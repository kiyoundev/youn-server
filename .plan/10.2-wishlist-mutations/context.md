# Issue #10.2: Context

## Issue Description

From `.doc/issues.md:878-893`:

> **Issue #10.2 — Wishlist Mutations (Add / Edit / Pause / Delete)**
> Add-item form (URL + name + target price) and per-row actions (edit target, pause/resume, delete) on `/wishlist`, against the already-built `POST`/`PATCH`/`DELETE /api/items` routes.
>
> **Coordination note with `#36`:** `#36`'s SSE broadcast only fires from the price-scraper, not from CRUD actions — a newly-added item won't appear via SSE, only on the next scrape cycle. Each mutation needs its own standard optimistic `mutate()` immediately after its `POST`/`PATCH`/`DELETE` response.

Blocked by `#36` (formerly `#10.1`), which shipped ✅ — the watchlist page already renders real data and has live SSE for scrape-driven updates. `#10.2` is unblocked.

**Original acceptance criteria:**
- [ ] Add item form submits and new item appears in table without full page reload
- [ ] Edit target, pause/resume, and delete actions all update the table without full page reload

**Reinterpretation surfaced during grilling** (see Target State below): pause/resume was written as a row-level (product-level) action, but the backend has no product-level "paused" field — it's purely derived (`compute_status`: all listings inactive → `"paused"`). Rather than a row action that bulk-toggles every listing (ambiguous once a listing can already be individually paused), pause/resume moved to a per-listing toggle in the sheet. The row-level dropdown keeps only Edit (opens sheet) and Delete.

## Component / Route Summary

### Current State

- `frontend/src/app/watchlist/page.tsx` — full UI shell (built ahead of blockers under #10.1), wired to real `GET /api/items` data via `#36`. Every *write* path is a `console.log` stub: Add Item dialog, inline sheet edits (name, target price, listing URL), add/remove listing, row-dropdown Delete. No pause/resume UI exists anywhere yet.
- `frontend/src/app/api/proxy/[...path]/route.ts` — only exports `GET`. Injects `X-API-Key` server-side so the browser never sees it. No POST/PATCH/DELETE handling.
- `backend/app/api/items.py` — full CRUD already implemented and tested: `POST/PATCH/DELETE /api/items/{id}`, `POST/PATCH/DELETE /api/items/{id}/listings/{id}`.
- `backend/app/schemas/product.py` — `ProductCreate` requires `url` (creates product + first listing atomically, in one call).
- `backend/app/schemas/listing.py` — `ListingUpdate` only has `active: bool | None` — **no way to PATCH a listing's URL today**.
- No toast/notification library, no established POST/PATCH/DELETE fetch pattern anywhere in the frontend — this is the first mutation slice in the codebase.

### Target State

**Add flow (bulk, one request — settled after two earlier revisions, see `challenges.md`):** `POST /api/items` takes `{name, target_price, urls: string[]}`, `urls` possibly empty. The backend in-batch-dedups, checks all candidate URLs against existing listings in one query, then probes the survivors' `retailer`/`scraper_type` **concurrently** (`asyncio.gather`, bounded by `asyncio.Semaphore(3)` — capped as insurance against a pathological large paste, verified safe against `PatchrightScraper`'s shared browser-context design; see `challenges.md`). A duplicate or unscrapable URL doesn't fail the request — it's reported in the response's `failed: [{url, detail}]` list, and the product plus every other successful listing are still created in one commit. The frontend makes exactly one request for the whole add (`createProduct`), reads `.product` and `.failed` from the result, `mutate('/api/proxy/items')`, one summary toast. Two earlier designs (sequential chained `createListing` calls; then that same chain moved to run in the background after the dialog closed) were built and then superseded once bulk-with-concurrent-probing turned out to solve the actual latency problem those designs were working around.

**Listing URL edit (new backend capability):** `ListingUpdate` gains `url: str | None`. `update_listing` re-runs the same duplicate-URL check `create_listing` already does, and re-derives `retailer`/`scraper_type` via the existing `_resolve_retailer_and_scraper_type` helper when `url` changes — otherwise a URL edit could leave a stale/wrong retailer badge. This preserves the listing's id and price history (the alternative, delete+recreate, silently wipes history and can cascade-delete the whole product if it's the last listing — rejected).

**Pause/resume (new UI, product-level — revised once after building it per-listing first):** One `Switch` in the sheet's Status row, next to the status badge, `checked={status !== "paused"}`. On toggle, bulk-`PATCH .../listings/{id} {active}` across every listing on the product (`Promise.allSettled`, no backend change needed — no product-level `active` field exists or was added, this still works purely by toggling every listing's real `active` column, same thing `compute_status` already derives `"paused"` from). The row-level dropdown (table) still does **not** get a pause/resume entry — same reasoning as before, plus the product-level switch now covers that gap from the sheet instead. A per-listing version was built first, then replaced after reconsidering: most users think "pause this item," not "pause this one retailer's listing," and a per-listing toggle reopens exactly the row-level-vs-individually-paused ambiguity grilling avoided, the moment a product-level control exists alongside it — resolved by not letting both exist at once.

**Delete:** Product delete gets a confirmation `Dialog` (irreversible, cascades all listings + all price history). Per-listing remove stays a direct click (already guarded: disabled when it's the product's last listing). If the deleted product's sheet is open, the sheet auto-closes.

**Proxy:** `route.ts` gains a shared `relay()` helper parameterized by HTTP method, used by `GET` (existing) and new `POST`/`PATCH`/`DELETE` exports — one place for the `X-API-Key` injection and status/body/content-type passthrough, including `204 No Content` (delete responses) not being forced into a JSON content-type.

**Error/success UX:** toast (`@base-ui/react/toast`, this repo's actual component system per `components.json`'s `base-nova` style — not sonner, an earlier wrong turn) on every mutation outcome. A `409` from a duplicate URL gets its own message ("That URL is already being watched") distinct from the generic failure toast.

**Update strategy:** await the mutation response, then `mutate('/api/proxy/items')` to refetch — no optimistic updates (no precedent for it in this codebase yet, and this app's real-world latency is low — local Pi backend).

## Impact & Risk

### Files Changed

- **`backend/app/schemas/product.py`** — `ProductCreate.url: str` (required) → `urls: list[str] = []` (bulk); `retailer`/`scraper_type` override fields dropped (meaningless once there can be multiple URLs). New `ListingFailure`, `ProductCreateResponse` schemas.
- **`backend/app/schemas/listing.py`** — `ListingUpdate` gains `url: str | None = None`, `retailer: str | None = None`.
- **`backend/app/schemas/validators.py`** — `validate_http_url` guards against `None` (needed by `ListingUpdate.url`).
- **`backend/app/api/items.py`** — `create_item` rewritten for bulk/concurrent/partial-success (in-batch dedup → existing-URL check → `asyncio.gather`-bounded probing → one commit); `update_listing` handles a `url` change (duplicate check + retailer/scraper_type re-derivation).
- **`backend/tests/api/test_items_routes.py`** — 8 `create_item` cases (known/unknown domain, probe failure, duplicate, in-batch collision, commit race, empty `urls`, multiple valid URLs) + `update_listing` URL-change/collision cases. Full suite: 274 passed.
- **`frontend/src/app/api/proxy/[...path]/route.ts`** — add `relay()` helper + `POST`/`PATCH`/`DELETE` exports.
- **`frontend/src/app/layout.tsx`** — mount `<Toaster />` once, app-wide.
- **`frontend/src/components/ui/toast.tsx`** (new, generated by `npx shadcn@latest add toast`) — Base UI toast primitives + a `toast` manager singleton.
- **`frontend/src/lib/toast.ts`** (new) — `toast.success()`/`toast.error()` sugar over the registry's `toast` manager.
- **`frontend/src/lib/api/items.ts`** (new) — thin fetch wrappers: `createProduct`, `createListing`, `updateProduct`, `updateListing`, `deleteProduct`, `deleteListing`, each throwing a typed error the callers can inspect for `status`. `createProduct` takes `{name, target_price, urls: string[]}`, returns `ProductCreateResult` (`{product, failed: ListingFailure[]}`) — not `Product` directly.
- **`frontend/src/app/watchlist/page.tsx`** — wire every stubbed write path to the wrappers above; add per-listing pause/resume toggle to the sheet; add product-delete confirm `Dialog`; close sheet on delete-of-open-product; toast on every outcome.

### Dependencies

- **`mutate` (SWR, `swr` package)** — already used by the SSE handler (`page.tsx:483-484,493`) for `/api/proxy/items` and per-listing history keys; every new mutation reuses the same `/api/proxy/items` key so SSE-driven and mutation-driven refetches stay on one consistent cache entry.
- **`listingHistoryKey` / `useListingHistory`** (`lib/hooks/use-listing-history.ts`) — unaffected; a newly-added listing gets its own `ListingHistoryFetcher` instance automatically once `/api/proxy/items` refetches and the row remounts its per-listing fetchers.
- **`sse-leader.ts`** — unaffected; this issue's mutations don't touch the SSE connection itself, only the same SWR cache keys it already refetches.
- **`_resolve_retailer_and_scraper_type`** (`backend/app/api/items.py:31-51`) — reused by `update_listing`'s new URL-change path, same as `create_item`/`create_listing` already do.

### New Dependencies

None. Toast UX uses `@base-ui/react/toast` (already a dependency) via `npx shadcn@latest add toast` — a file-generation step, not a package install. No toast component existed in `components/ui/` before this issue; later slices (`#10.4` stocks CRUD) will reuse `lib/toast.ts`'s `toast.success()`/`toast.error()`.
