# Issue #60: Schema & API Contract

## Migration `0020_listing_used_price.py`
- Revision `"0020"`, previous revision `"0019"`.
- `upgrade`: add `watch_items.used_price` as `Float`/`Numeric` matching `last_price`'s type, nullable, no default.
- `downgrade`: drop the column.
- Deploy order on the Pi: build → `run --rm backend alembic upgrade head` → `up -d backend`, so the column exists before code that writes it.

## Model
`Listing.used_price: Mapped[float | None]` next to `last_price`.

## Scraper result
`ScraperResult.used_price: float | None = None` (frozen dataclass, default keeps every other scraper unchanged). Set only by `AmazonCAScraper` on an `oos` result from a used-only page.

## Persistence rule (`process_item`)
| Result | `used_price` |
|--------|--------------|
| `oos` with `used_price` | set to that value |
| `oos` without | set to `NULL` |
| `ok` | cleared to `NULL` |
| `error` | unchanged (keeps the last known info) |

No `PriceHistory` row, no `Event`, no product-level price recalculation for `used_price`.

## API
The listing object returned with the product gains `used_price: float | null`. No new routes. Frontend type gains the same field.

## UI contract
Retailer row: name, `ExternalLink` button, then an info icon (`Info`, in a `Tooltip`) shown only when `last_scrape_status === "oos"` and `used_price !== null`. Tooltip text: `Used available at {fmtPrice(used_price, displayCurrency)}`. Shown alongside the error icon pattern, never together with it (error and oos are exclusive).
