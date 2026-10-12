# Issue #58: Schema & API Contract

No app API routes, Server Actions or DB schema change. The contract that matters is Uniqlo's commerce API, which `UniqloScraper` consumes, and the `ScraperResult` it produces.

## External API Contracts

### Uniqlo commerce API — product variants (internal, undocumented)

```
GET https://www.uniqlo.com/{region}/api/commerce/v5/{lang}/products/{productId}/price-groups/{priceGroup}/l2s
    ?withPrices=true&withStocks=true&includePreviousPrice=false&httpFailure=true
Headers: x-fr-clientid: uq.ca.web-spa      (Canada; looked up from a region table)
         Accept: application/json, a normal browser User-Agent
```

- **From the stored listing URL** `https://www.uniqlo.com/ca/en/products/E491096-000/00?colorDisplayCode=67&sizeDisplayCode=004`:
  - `region` = `ca`, `lang` = `en` (path segments 1 and 2)
  - `productId` = `E491096-000`, `priceGroup` = `00` (default `00` if the third segment is absent)
  - `colorDisplayCode` / `sizeDisplayCode` from the query (both optional)
- **Success:** HTTP 200, `{"status": "ok", "result": {"l2s": [...], "stocks": {...}, "prices": {...}, "bookingCenters": [...]}}`.
- **Failure:** HTTP 400 `{"status": "nok", "error": {"details": [{"message": "invalid or missing client id"}]}}` (seen with a missing header).

Response shape, from the two real captures:

```jsonc
"l2s": [{
  "color": {"code": "COL67", "displayCode": "67"},
  "size":  {"code": "SMA004", "displayCode": "004"},
  "l2Id": "09622126",            // key into stocks and prices
  "sales": true
}],
"stocks": {"09622126": {"statusCode": "IN_STOCK", "quantity": 11, "backInStock": false, "statusLocalized": "In stock"}},
// sold-out example: {"statusCode": "STOCK_OUT", "quantity": 0, "backInStock": true, "statusLocalized": "Out of stock"}
"prices": {"09622126": {"base": {"currency": {"code": "CAD"}, "value": 79.9}, "promo": null, "taxPolicy": "EXCLUSIVE"}}
```

## Mapping to `ScraperResult`

| Case | Result |
|---|---|
| Variant (color + size) found, in stock | `ScraperResult(price, "ok", currency)` |
| Variant found, sold out | `ScraperResult(price, "oos", currency)` — price kept, as `IKEAScraper` does |
| No color/size in URL | Variant rule below; all sold out → `oos` (price of the first variant), else `ok` at the first in-stock variant |
| Color only | Same rule restricted to that color |
| Color/size given but not in `l2s` | `error`, `"variant color=67 size=004 not found for E491096-000"` — never silently substitute another variant |
| Region other than `ca` | `error`, `"unsupported Uniqlo region 'us'"` |
| URL has no `E…-…` product ID | `error`, `"no Uniqlo product ID found in URL"` |
| HTTP non-200 or `status != "ok"` | `error`, with the API's own message (e.g. `invalid or missing client id`) so a rotated client ID is diagnosable from the UI |
| Network/parse exception | `error`, `_describe_exception(exc)` |

- **Price:** `prices[l2Id].promo.value` if `promo` is not null, else `base.value`.
- **Currency:** `base.currency.code`, kept only if in `{"USD","CAD","KRW"}`, else `None`.
- **In stock:** `quantity > 0` and `statusCode != "STOCK_OUT"`. Unknown status codes with a positive quantity count as in stock (see `challenges.md`).
- **`restock_at`:** left `None`. `backInStock: true` on a sold-out item looks like a "notify me" flag, not a date.
- **`site_name` / `product_title`:** not set; the user supplies the item name, and the retailer label comes from `_derive_retailer("uniqlo.com")` = "Uniqlo".

## Config

```python
# scraper/config.py
UNIQLO_CLIENT_IDS: dict[str, str] = {"ca": "uq.ca.web-spa"}
```
