# Issue #10.2: Schema & API Contract

## Backend Changes

### `ProductCreate` (`backend/app/schemas/product.py`)

Revised after further grilling — see `challenges.md` for the full trade-off history. Final shape is **bulk, not chained**: zero or more URLs in one request, probed concurrently (bounded), partial success representable in the response instead of via per-URL frontend calls.

```python
class ProductCreate(BaseModel):
    name: str
    target_price: float
    urls: list[str] = []            # was, in order: url: str (required) -> url: str | None -> this

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, value: list[str]) -> list[str]:
        for url in value:
            validate_http_url(url)
        return value
```
`retailer`/`scraper_type` override fields were dropped from `ProductCreate` entirely — a single override field doesn't make sense once there can be multiple URLs, each potentially a different retailer. Per-URL overrides still exist where they're meaningful: `ListingCreate` (`POST /api/items/{id}/listings`, unchanged, still `{url, retailer?, scraper_type?}`).

Confirmed (`backend/app/schemas/validators.py`): `validate_http_url(value: str)` calls `urlparse(value)` unconditionally — passing `None` through as-is would crash inside `urlparse`, not raise a clean Pydantic `ValidationError`. Fixed at the validator: guards `if value is None: return value` at the top, before `urlparse`. Still needed even after `ProductCreate` moved off `url: str | None` — `ListingUpdate.url` (below) is optional and reuses the same validator.

```python
class ListingFailure(BaseModel):
    url: str
    detail: str

class ProductCreateResponse(BaseModel):
    product: ProductResponse
    failed: list[ListingFailure] = []
```
`POST /api/items`'s actual response shape — not `ProductResponse` alone, since a partial add (some URLs succeeded, some didn't: duplicate, in-batch collision, or unscrapable) needs representing in one response rather than silently dropping which URLs failed and why.

### `ListingUpdate` (`backend/app/schemas/listing.py`)
```python
class ListingUpdate(BaseModel):
    active: bool | None = None
    url: str | None = None          # new
    retailer: str | None = None     # new — explicit override, same semantics as ListingCreate

    _validate_url = field_validator("url")(validate_http_url)  # must tolerate None
```

## API Routes

### `POST /api/items` (modified — bulk, concurrent, partial-success)
- **Handler:** `backend/app/api/items.py::create_item`
- **Request:** `ProductCreate` — `{name, target_price, urls: string[]}`, `urls` may be empty.
- **Behavior:**
  1. In-batch dedup — two identical URLs in one request; the second is marked failed (`"Duplicate URL within this request"`) before ever touching the DB.
  2. One `SELECT ... WHERE url IN (...)` against the survivors — any that already exist are marked failed (`"An item with this URL already exists"`).
  3. Remaining URLs are probed **concurrently**, bounded by `asyncio.Semaphore(_PROBE_CONCURRENCY)` (`= 3`) — each probe is `_resolve_one`, a non-raising wrapper around the existing `_resolve_retailer_and_scraper_type`; an unscrapable URL becomes a `failed` entry (`"URL could not be scraped by any available method"`), not an aborted request.
  4. Product + every successful `Listing` are added to the session, one commit.
- **Response:** `ProductCreateResponse` — `{product: ProductResponse, failed: [{url, detail}]}`. Still `201` even when `failed` is non-empty, as long as the product itself was created.
- **Error cases:** `422` (malformed URL, `urls` validator), `409` only for the rare commit-time race (a URL passed the existing-URL check but got claimed by another request before this one's commit — `IntegrityError` can't say which row, so the whole create fails here rather than guessing). Everything else that used to be a `400`/`409` for the whole request now lands in `failed` instead.

**Why concurrent, and why capped at 3:** each probe can be a real network round-trip to the retailer's own site, escalating to a headless-browser page load (`PatchrightScraper`) if a plain HTTP fetch fails — sequential probing meant total wait ≈ sum of every URL's probe time. Concurrent probing brings that down to ≈ the slowest single probe. Verified before building this: `PatchrightScraper` uses one shared, persistent browser **context** (class-level, started once), and each call just opens/closes its own page within it — concurrent pages in one context is a normal, supported Playwright pattern, not "spin up N browser processes." Capped anyway, because the scheduler's own scraping loop (`jobs.py`'s `poll_prices` → `_process_item`) runs strictly sequentially today — no part of this codebase has driven the scraper concurrently before this, and the Pi 5 8GB runs every other service in the stack too. At this app's realistic 1-3 URLs/add, the cap never engages; it only throttles an atypically large paste.

### `PATCH /api/items/{product_id}/listings/{listing_id}` (modified)
- **Handler:** `backend/app/api/items.py::update_listing`
- **Request:** `ListingUpdate` — `active`, `url`, `retailer` all optional, partial update.
- **Behavior change:** when `url` is provided and differs from the current value:
  1. Check for an existing `Listing` with that URL (excluding this listing's own id) → `409` if found, same message as `create_listing`.
  2. Re-derive `retailer`/`scraper_type` via `_resolve_retailer_and_scraper_type(new_url, body.retailer, None)` — always re-detect `scraper_type` on a URL change (no `scraper_type` override field exposed on `ListingUpdate`, matching `ListingCreate`'s "explicit override or auto-detect" pattern already used elsewhere).
  3. Apply `listing.url`, `listing.retailer`, `listing.scraper_type`.
- **Response:** `ListingResponse` — id and price history (via `watch_item_id` FK) unchanged, only editable fields updated.
- **Error cases:** `404` (listing/product mismatch, existing), `409` (duplicate URL, new for this route), `400` (scraper detection failure on the new URL, new for this route — reuse `create_item`'s existing `HTTPException(400, ...)` pattern).

### `POST /api/proxy/[...path]` (new)
### `PATCH /api/proxy/[...path]` (new)
### `DELETE /api/proxy/[...path]` (new)
- **Handler:** `frontend/src/app/api/proxy/[...path]/route.ts`
- **Request:** relayed as-is — path, query string, and JSON body forwarded to `${BACKEND_URL}/api/${path}`, with `X-API-Key` injected server-side (never present in the original browser request).
- **Response:** backend's status, body, and `Content-Type` relayed verbatim — including `204 No Content` from `DELETE`, which must not be forced into `application/json`.
- **Error cases:** whatever the backend route returns (`400`/`404`/`409`) passes through unchanged; the proxy itself adds no new error cases.

```typescript
// route.ts — shared helper
type RouteContext = { params: Promise<{ path: string[] }> }

async function relay(request: NextRequest, path: string[], method: string) {
  const apiKey = process.env.API_KEY
  if (!apiKey) {
    // Fail loud here rather than send an empty X-API-Key — the backend
    // would still reject that with its own 401 "Invalid API key"
    // (indistinguishable from a real bad-credential case). This instead
    // tells you specifically that the Next.js server's own env is
    // misconfigured, not that the backend rejected an actual auth attempt.
    return NextResponse.json(
      { detail: "Proxy misconfigured: API_KEY environment variable is not set" },
      { status: 500 },
    )
  }

  const url = `${BACKEND_URL}/api/${path.join("/")}${request.nextUrl.search}`
  const hasBody = method !== "GET" && method !== "DELETE"
  const resp = await fetch(url, {
    method,
    headers: {
      "X-API-Key": apiKey,
      ...(hasBody ? { "Content-Type": "application/json" } : {}),
    },
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  })
  const body = await resp.text()
  return new NextResponse(body || null, {
    status: resp.status,
    headers: body ? { "Content-Type": resp.headers.get("Content-Type") ?? "application/json" } : {},
  })
}

export async function GET(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "GET")
}
export async function POST(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "POST")
}
export async function PATCH(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "PATCH")
}
export async function DELETE(req: NextRequest, ctx: RouteContext) {
  return relay(req, (await ctx.params).path, "DELETE")
}
```

## TypeScript Interfaces

```typescript
// frontend/src/lib/api/items.ts — request payloads, mirroring the backend schemas above
export interface ProductCreatePayload {
  name: string;
  target_price: number;
  urls: string[];
}

export interface ListingCreatePayload {
  url: string;
}

export interface ProductUpdatePayload {
  name?: string;
  target_price?: number;
}

export interface ListingUpdatePayload {
  active?: boolean;
  url?: string;
}

// Mirrors backend's ListingFailure/ProductCreateResponse — createProduct's
// actual return shape, since a partial add needs representing in one value.
export interface ListingFailure {
  url: string;
  detail: string;
}

export interface ProductCreateResult {
  product: Product;
  failed: ListingFailure[];
}

// Thrown by every wrapper on a non-2xx response so callers can branch on status
// (e.g. 409 -> "already watched" toast vs. generic failure toast).
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}
```

`ProductResponse`/`ListingResponse` themselves are unchanged (`watchlist/page.tsx`'s existing `Product`/`Listing` interfaces stay as-is) — only request-side payload types and `createProduct`'s specific return shape are new.
