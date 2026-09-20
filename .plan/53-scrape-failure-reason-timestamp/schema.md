# Issue #53: Schema & Data Contract

No new API routes — existing `GET /api/items`, `GET /api/items/{id}` response shapes gain a field; no new endpoints.

## Database — Alembic Migration `0017`

```python
def upgrade() -> None:
    op.add_column("watch_items", sa.Column("last_scrape_error", sa.String(), nullable=True))
    op.add_column("watch_items", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("watch_items", "last_checked_at")
    op.drop_column("watch_items", "last_scrape_error")
```

Two columns, no backfill. (An earlier draft also had `last_failed_at`; dropped before shipping — once `last_checked_at` became "last attempt, any outcome" it always equalled it while a listing was failed and cleared on recovery, so it carried no information of its own.)

## SQLAlchemy Model — `Listing` (`models/watch_item.py`)

```python
last_scrape_error: Mapped[str | None] = mapped_column(String, nullable=True)
last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- `last_scrape_error` — short machine-written reason, never a traceback. Set on `"error"`, cleared on the next `"ok"`/`"oos"`.
- `last_checked_at` — when the listing was last polled, **whatever the outcome** (`ok`, `oos`, `error`). Source of the UI's "last checked", replacing `MAX(PriceHistory.checked_at)` (blind to `oos`/`error`, since `PriceHistory` is only written on `ok`). The last *successful* price time stays available in `PriceHistory`.

## Dataclass — `ScraperResult` (`services/scraper/result.py`)

```python
error_reason: str | None = None
```

Set only on `status="error"`. A short machine-written string, not a traceback (full tracebacks stay in logs only, via existing `exc_info=True` calls).

**Population by call site:**

| Site | `error_reason` value |
|---|---|
| `http_scraper.py` generic `except Exception:` | `_describe_exception(exc)` |
| `patchright_scraper.py`'s `PatchrightScraper.get_price` generic `except Exception:` | `_describe_exception(exc)` |
| `patchright_scraper.py`'s `AmazonCAScraper.get_price` browser-launch-failure `except Exception:` | `_describe_exception(exc)` |
| `patchright_scraper.py`'s `AmazonCAScraper.get_price` retry-exhaustion return | `"exhausted retries"` (fixed string — per-attempt exceptions stay DEBUG-only, not surfaced individually) |
| `ikea_scraper.py` no item number found in the URL path | `"no item number found in URL"` |
| `ikea_scraper.py` missing `<script type="text/hydrate">` payload | `"availability data missing from IKEA response"` |
| `ikea_scraper.py` generic `except Exception:` | `_describe_exception(exc)` |
| `base.py`'s `_run_hierarchy` silent no-price-found return | Content-detected: `"Cloudflare bot-check challenge did not clear"` / `"Akamai bot-block (access denied)"` / generic `"no price found on page"` |
| `jobs.py`'s `ok` + `price is None` transition | `"scraper returned ok status but no price was found"` |
| `jobs.py`'s `_bounded_process_item` backstop (unexpected exception escaping `process_item` while the listing is still never-scraped) — a fourth place that sets `"error"` | `_describe_exception(exc)` |
| `jobs.py`'s `"error"` branch | `scrape.error_reason or "unknown scraper error"` — guarantees non-empty even if a future scraper forgets to set one |

All `"error"` writes go through one helper, `_record_failure(listing, reason, now)` (sets `last_scrape_status`, `last_scrape_error`, `last_checked_at`); a real `ok`/`oos` result calls `_clear_failure(listing)` (clears `last_scrape_error`) and sets `last_checked_at` itself.

### Helper — `_describe_exception(exc) -> str` (`base.py`)

Raw `str(exc)` isn't safe to persist: it can be empty (`httpx.ConnectError("")`, a bare `TimeoutError()` — breaking the "non-empty" guarantee) or a multi-line Playwright call log (unreadable in a tooltip). The helper returns `"TypeName: first line of message"`, the type name alone when the message is empty, truncated to 200 characters.

| Exception | Result |
|---|---|
| `httpx.ConnectError("refused")` | `"ConnectError: refused"` |
| `TimeoutError()` | `"TimeoutError"` |
| Playwright `TimeoutError("Page.goto: Timeout 30000ms exceeded.\nCall log:\n...")` | `"TimeoutError: Page.goto: Timeout 30000ms exceeded."` |

### Helper — `_detect_bot_block(soup) -> str | None` (`base.py`)

Run only when every extraction method has already come up empty. Page-content signatures, not a flag threaded from a specific scraper: title contains "just a moment" → Cloudflare; title contains "access denied" **and** the text mentions `edgesuite` or `reference #` → Akamai; anything else → `None` (caller falls back to the generic reason). Two known signatures, not an exhaustive detector.

## API Response Schema — `ListingResponse` (`schemas/listing.py`)

```python
class ListingResponse(BaseModel):
    id: int
    retailer: str
    url: str
    last_price: float | None
    last_scrape_status: Literal["ok", "oos", "error"] | None
    restock_at: str | None
    last_scrape_error: str | None   # new
    last_checked: datetime | None   # existing field, new source (Listing.last_checked_at, not PriceHistory)
    product_id: int
    created_at: datetime
    model_config = {"from_attributes": True}
```

## Frontend TypeScript — `Listing` (`lib/api/items.ts`)

```typescript
export interface Listing {
  id: number;
  retailer: string;
  url: string;
  last_price: number | null;
  last_scrape_status: "ok" | "oos" | "error" | null;
  restock_at: string | null;
  last_scrape_error: string | null;  // new
  last_checked: string | null;       // now "last poll attempt, any outcome"
  product_id: number;
  created_at: string;
}
```

**`last_scrape_error` is `null` for listings already in `"error"` at deploy time** (they predate persistence) until their next scrape — the UI renders `"no details recorded yet"` rather than `null`/`undefined`.

No change needed to `WatchStatus` or `Product` — `"failed"`/`"out_of_stock"` statuses already exist; this issue only adds *why* detail underneath the existing status values, not new status values.
