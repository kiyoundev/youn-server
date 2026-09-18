# Issue #53: Schema & Data Contract

No new API routes — existing `GET /api/items`, `GET /api/items/{id}` response shapes gain fields; no new endpoints.

## Database — Alembic Migration `0017`

```python
def upgrade() -> None:
    op.add_column("watch_items", sa.Column("last_scrape_error", sa.String(), nullable=True))
    op.add_column("watch_items", sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("watch_items", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("watch_items", "last_checked_at")
    op.drop_column("watch_items", "last_failed_at")
    op.drop_column("watch_items", "last_scrape_error")
```

One migration for all three — tightly related, shipped together, matches the precedent of `0016`'s single-column-add shape.

## SQLAlchemy Model — `Listing` (`models/watch_item.py`)

```python
last_scrape_error: Mapped[str | None] = mapped_column(String, nullable=True)
last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

## Dataclass — `ScraperResult` (`services/scraper/result.py`)

```python
error_reason: str | None = None
```

Set only on `status="error"`. A short machine-written string, not a traceback (full tracebacks stay in logs only, via existing `exc_info=True` calls).

**Population by call site:**

| Site | `error_reason` value |
|---|---|
| `http_scraper.py` generic `except Exception:` | `str(exc)` |
| `patchright_scraper.py`'s `PatchrightScraper.get_price` generic `except Exception:` | `str(exc)` |
| `patchright_scraper.py`'s `AmazonCAScraper.get_price` browser-launch-failure `except Exception:` | `str(exc)` |
| `patchright_scraper.py`'s `AmazonCAScraper.get_price` retry-exhaustion return | `"exhausted retries"` (fixed string — per-attempt exceptions stay DEBUG-only, not surfaced individually) |
| `base.py`'s `_run_hierarchy` silent no-price-found return | Content-detected: `"Cloudflare bot-check challenge did not clear"` / `"Akamai bot-block (access denied)"` / generic `"no price found on page"` |
| `jobs.py`'s new `ok` + `price is None` transition | `"scraper returned ok status but no price was found"` |

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
    last_failed_at: datetime | None # new
    last_checked: datetime | None   # existing field, new source (last_checked_at, not PriceHistory)
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
  last_failed_at: string | null;     // new
  last_checked: string | null;
  product_id: number;
  created_at: string;
}
```

No change needed to `WatchStatus` or `Product` — `"failed"`/`"out_of_stock"` statuses already exist from this session's earlier work; this issue only adds *why*/*when* detail underneath the existing status values, not new status values.
