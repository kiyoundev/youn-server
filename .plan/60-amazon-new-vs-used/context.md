# Issue #60: Context

## Issue Description
`AmazonCAScraper` reads one price off the product page and can't tell new from used. When all new units are sold out and only used remain, the tracked price can become a used price, which looks like a price drop on the new item and fires a false alert.

User context: used items are only wanted in rare bargain cases, so the default must be "new only", with used shown as information.

Acceptance criteria: see `_index.md`.

## Settled Decisions
1. **Scope** — part 1 + 1b now; the used-condition listing (`Listing.condition`, add-used UI, condition label) is deferred.
2. **Used-only page = `oos`** — "all new sold out" maps to the existing `oos` status (same as no-featured-offer).
3. **Used price as info, not data** — a nullable `Listing.used_price`, shown as an info icon next to the retailer's link button (same placement as the error icon). No `PriceHistory` row, no chart, no alert.
4. **New-price read is strict** — only inside the new buy box; not found → `error` with a specific reason. The page-wide `.a-offscreen` regex fallback is removed.
5. **Parse `page.content()` in Python** (BeautifulSoup) instead of browser locators, so every selection rule is testable with real HTML (today `_find_price_text` is patched out in all tests).
6. **Used price comes only from the used-only box** — "See all buying options" / no-featured-offer pages show no used price. The "Other sellers" box is not parsed (decided 2026-10-12). Accepted.
7. **New price is found by an ancestor walk from `#add-to-cart-button`** — the nearest ancestor containing a `.apex-pricetopay-value`, then its first `.a-offscreen` with non-empty text. Works in both the plain and the accordion layout and can never reach the used row (a sibling) or the empty/label-only title-price block. `[data-pricetopay-label]` is **not** used (it reflects the featured offer, including used, and carries "with N percent savings" text). The `customerVisiblePrice` hidden input is only a fallback, read inside the same ancestor.

## Component / Route Summary

### Current State
- `patchright_scraper.py` `AmazonCAScraper.get_price`: retry loop; ASIN mismatch → `variant_gone` → `oos`; `_amazon_has_no_new_offer(html)` → `oos`; else `_find_price_text(page)` → `ok` CAD.
- `_amazon_has_no_new_offer`: exact-id `add-to-cart-button` overrides markers `usedOnlyBuybox`, `unqualifiedBuyBox`, `fod-cx-box`, `outOfStock`. The used box's button is `add-to-cart-button-ubb`, so it is not confused.
- `_find_price_text`: first `[data-pricetopay-label]`, else the first `$` text in any `.a-offscreen`/`.aok-offscreen`. On a used-only page this can grab an unrelated price (likely cause of the false drop). The both-offers capture has no `data-pricetopay-label`, so the first branch may not even match in the accordion layout.
- `Listing` (table `watch_items`) has `last_price`, `last_scrape_status`, `restock_at`, `last_scrape_error`; no used price.

### Real amazon.ca captures (2026-10-12)
| Page | Markup | Outcome |
|------|--------|---------|
| `B0GSRYXZM5` no offers | `#fod-cx-box` "No featured offers available" | `oos`, no used price |
| `B0GSS5TK8R` used only | `#usedOnlyBuybox` > `#usedBuySection .offer-price` = `$637.19`, condition "Used: Very Good" | `oos`, used price `637.19` |
| `B0FQFPN3WR` new + used (accordion) | `#newAccordionRow_0` (new, $54.98) and `#usedAccordionRow` (used, $52.13) | `ok` at `54.98` |
| `B073S5JHRV` new only (plain) | `#add-to-cart-button` (`type="button"`), price in `#apex_offerDisplay_desktop .apex-pricetopay-value .a-offscreen` = `$88.00`; "Other sellers: New (3) from $88.00" box outside the buy box | `ok` at `88.00` |

Both-offers traps: `corePrice_feature_div`, `apex_offerDisplay_desktop`, `addToCart_feature_div` ids appear in both rows; the used row's form contains `twister-plus-price-data-price` = the *new* price. The new row's form holds `items[0.base][customerVisiblePrice][amount]` = `54.98` and `currencyCode` = `CAD`; the plain-layout capture shows no such inputs (the form may sit above the copied fragment).

### Scraper-side captures (local container, 2026-10-12, full `page.content()`)
Same markers and prices as the browser captures; no captcha, no ASIN redirect; the price is in the saved HTML (not injected after load).
- Two price blocks exist. `#corePrice_feature_div` (inside the buy box / accordion row) holds `.apex-pricetopay-value .a-offscreen` with a clean `$54.98`. `#corePriceDisplay_desktop_feature_div > #apex_desktop` (the price under the title) has an **empty** `.apex-pricetopay-value` and carries the text in `span#apex-pricetopay-accessibility-label[data-pricetopay-label]` instead.
- That label shows whatever offer is featured: on the used-only page it reads `$637.19` (the used price), and on a discounted offer its text is `"$52.13 with 5 percent savings"`. `_parse_price` turns that into `52.135` (and `"$1,299.00 with 12 percent savings"` into `1299.0012`), i.e. the old first-choice locator already corrupts discounted prices.
- Ancestor walk checked on the real HTML: plain page → nearest ancestor of `#add-to-cart-button` with a `.apex-pricetopay-value` yields exactly `['$88.00']`; accordion page → `['$54.98']` (the used row is outside it). The empty nodes are never in scope.
- `customerVisiblePrice` amounts are page-wide lists (`['637.19']` on used-only, `['54.98','52.13','54.98']` on accordion) — usable only inside the walked ancestor, never page-wide.

### Target State
- `_amazon_new_price(html) -> float | None`: find the exact-id `#add-to-cart-button`; walk up to the nearest ancestor containing a `.apex-pricetopay-value`; return its first `.a-offscreen` as a number. If the class is missing, fall back to `customerVisiblePrice[amount]` within that ancestor; else `None` (→ `error`). Never scans outside that ancestor.
- `_amazon_used_price(html) -> float | None`: first non-empty `#usedBuySection .offer-price`.
- `get_price` uses both on the one `page.content()` it already fetches.
- `ScraperResult.used_price`, persisted to `Listing.used_price` by `process_item`, exposed by the API, rendered as an info icon.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/patchright_scraper.py`** — parsers, `get_price` wiring, remove page-wide fallback.
- **`backend/app/services/scraper/result.py`** — `used_price: float | None = None`.
- **`backend/app/models/watch_item.py`** + **`backend/alembic/versions/0020_listing_used_price.py`** (new) — nullable column.
- **`backend/app/scheduler/jobs.py`** — set on `oos`, clear on `ok`.
- **Listing API schema** — `used_price`.
- **`frontend/src/app/watchlist/page.tsx`** (+ type) — info icon.
- **`backend/tests/scraper/test_amazon.py`** — fixtures and parser tests.
- **`.doc/issues.md`** — rewrite #60 criteria, add deferred issue.

### Dependencies
- **#61** — a used-only result is `oos`, so `oos → ok` restock logic keeps working unchanged.
- **#59/#52** — none.
