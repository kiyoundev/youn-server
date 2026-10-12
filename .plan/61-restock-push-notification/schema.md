# Issue #61: Schema & API Contract

No API routes change. The data model gains one event type.

## Migration `0019_events_restock_type.py`
- Revision `"0019"`, previous revision `"0018"` (this repo uses short numeric revision ids).
- `upgrade`: drop `ck_events_type`, recreate it as `type IN ('PRICE_DROP', 'STOCK_THRESHOLD', 'RESTOCK')`.
- `downgrade`: drop it and recreate the two-value constraint. Fails if `RESTOCK` rows exist, so delete them first (see `challenges.md`).

## Event payload (`events.payload`, JSONB)
```python
{
    "product_id": int,
    "listing_id": int,   # the restocking listing, not the cheapest
    "retailer": str,
    "price": float,      # that listing's price, native currency
    "url": str,
}
```
Same shape as `PRICE_DROP`.

## Notification (`notify._format_restock`)
| Field | Value |
|-------|-------|
| Title | `Back in Stock: {product.name}` |
| Body | `Now {format_price(price, product.currency)} at {retailer}` |
| URL | `payload["url"]` |
| Priority | normal (0) |

Raises `ValueError` if the product is missing, like `_format_price_drop`.

## Transition rule
`RESTOCK` is inserted only when the listing's status, re-read under `FOR UPDATE` after the scrape, is exactly `"oos"` and the new result is `ok` with a price. A previous `None`, `"error"` or `"ok"` produces no event.
