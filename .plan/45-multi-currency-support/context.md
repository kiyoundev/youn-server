# Issue #45: Context

## Issue Description

Every price in the app displays with a hardcoded `$` — table Best Price, target price,
sheet-panel listing prices, and the price-history chart tooltip (which today shows a bare
unprefixed number, e.g. `52`, not even `$52`). Silently wrong for non-USD/CAD sites: a Korean
retailer quoting ₩52,000 is parsed as a raw number and shown as `$52`, no conversion, no
indication anything's off.

**Descoped from the original issue text during grill-me** (2026-08-19, product owner decision):
currency is **product-level, not per-listing**. A single product's retailer listings are always
in one currency — no mixed CAD/USD/KRW within one product. This eliminates per-listing FX
conversion for the alert/"cheapest" comparison and the `Listing.currency` column/override
entirely. Scope is now: detect one currency per product from its scrapes, store it on `Product`,
display it correctly everywhere, let the user override it. Only 3 currencies in practice: USD,
CAD (default), KRW.

**FX conversion re-added mid-planning, narrower than originally scoped**: the watchlist page's
header total (`totalBestPrice`, sum of every product's best price) is meaningless if summed raw
across currencies — a KRW product's ₩30,000 and a USD product's $50 can't just be added.
That total needs FX conversion to CAD. Per product owner (2026-08-19): the *total* is
FX-converted to CAD; individual table rows stay in native currency (converting a row would make
it impossible to tell whether a price notification moved because the product's price changed or
because the FX rate moved); the sheet panel shows **both** the native-currency figure and its
FX-converted CAD equivalent, so detail view has both pieces of information at once. Alert/target
comparison logic is unaffected — still native-currency-only, per product.

### Acceptance criteria (revised scope)
- [ ] Table (Best Price / Target Price) displays native currency with correct formatting
      (not hardcoded `$`)
- [ ] Header total sums every product's best price converted to CAD
- [ ] Sheet panel shows both native-currency price and FX-converted CAD equivalent, per listing
      and for target_price
- [ ] Chart tooltip shows native currency (fixes the existing missing-`$` bug), unaffected by FX
- [ ] Currency auto-detected from the scraped page, rolled up to `Product.currency` on first
      successful scrape that yields a currency
- [ ] User can manually set/override a product's currency (dropdown next to target_price);
      override always wins over auto re-detection
- [ ] `min(available_listings, key=last_price)` / target_price alert comparison unchanged — still
      native-currency-only, no FX involved
- [ ] FX rate fetched daily, cached; if stale (>24h since last successful fetch), last-known rate
      is still used, with a small stale-indicator icon shown next to FX-converted figures
- [ ] Existing (mock) products are unaffected in practice — acceptable for `currency` to start
      NULL and resolve on next scrape, since current data is sample/mock

## Component / Route Summary

### Current State
- `ScraperResult` (`backend/app/services/scraper/result.py`) carries `price`, `status`,
  `site_name`, `product_title` (issue #44) — no currency field.
- `BaseScraper._run_hierarchy` (`backend/app/services/scraper/base.py`) is the single shared
  extraction point: parses HTML once, runs 4 price-extraction methods in priority order, then a
  separate site_name/product_title inference pass, and returns one `ScraperResult`.
- `AmazonCAScraper` (`backend/app/services/scraper/patchright_scraper.py:246`) is a dedicated
  amazon.ca scraper with its own extraction path (`_find_product_title`), bypassing the generic
  hierarchy — no site_name/currency detection needed since the site is fixed.
- `Product` model (`backend/app/models/product.py`) has no currency field; `target_price: float`
  is unitless today.
- `Listing` model (`backend/app/models/watch_item.py`) has `last_price: float | None`, also
  unitless.
- `process_item` job (`backend/app/scheduler/jobs.py:190-229`) rolls up listings to find the
  cheapest available one, compares against `product.target_price` with raw `<=`/`>` — already
  currency-safe once the one-currency-per-product assumption holds.
- Frontend `watchlist/page.tsx` hardcodes `$` in 4 places: `fmtPrice` helper (`$${value}`),
  Best Price table cell, Target Price table cell, sheet-panel per-listing price, and the
  sheet-panel target_price inline editor.
- `product-price-chart.tsx` chart tooltip shows a bare number (Recharts default tooltip
  formatting) — no `$` at all today, a separate existing bug this issue also fixes.
- Schemas: `ProductCreate`/`ProductUpdate`/`ProductResponse` (`backend/app/schemas/product.py`)
  have no currency field.

### Target State
- `ScraperResult` gains `currency: str | None = None` (ISO 4217, one of `"USD"`, `"CAD"`,
  `"KRW"`), inferred in `_run_hierarchy` alongside the existing site_name/product_title pass.
- `Product` gains a nullable `currency: str | None` column (migration), backfilled from the
  first successful scrape that yields a currency (fill-only-if-null, same pattern as
  `Product.name`), unless the user has manually set it — manual set always wins.
- `ProductCreate`/`ProductUpdate`/`ProductResponse` gain `currency: Literal["USD","CAD","KRW"] |
  None`.
- `AmazonCAScraper` hardcodes `currency="CAD"` on its `ScraperResult` (known single site, no
  need to run generic detection).
- Frontend gets one shared price-formatting helper applied at all 4 hardcoded-`$` sites plus the
  chart tooltip; a currency dropdown (USD/CAD/KRW) added next to the existing target_price
  inline editor in the sheet panel.
- Format: `USD` → `$100 USD`; `CAD` (default) → `$120` (no suffix, matches today's display
  exactly); `KRW` → `₩52,000` (no decimals, symbol itself is unambiguous). `currency === null`
  → bare unprefixed number (matches today's chart-tooltip bug during the unresolved window).

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/result.py`** — add `currency` field to `ScraperResult`
- **`backend/app/services/scraper/base.py`** — add `_extract_currency` detection pass, wire into
  `_run_hierarchy`
- **`backend/app/services/scraper/patchright_scraper.py`** — `AmazonCAScraper` hardcodes
  `currency="CAD"`
- **`backend/app/models/product.py`** — add nullable `currency` column
- **`backend/alembic/versions/`** — new migration adding `products.currency`
- **`backend/app/schemas/product.py`** — add `currency` to `ProductCreate`/`ProductUpdate`/
  `ProductResponse`
- **`backend/app/scheduler/jobs.py`** — fill `Product.currency` from scrape result
  (fill-only-if-null), same guarded block as the existing `product.name` inference
- **`frontend/src/app/watchlist/page.tsx`** — shared currency-format helper, applied to Best
  Price / Target Price / sheet-panel listing prices; currency dropdown next to target_price edit
- **`frontend/src/components/ui/product-price-chart.tsx`** — chart tooltip formatted with
  currency (fixes the existing missing-`$` bug)
- **`frontend/src/lib/api/items.ts`** — `Product` type gains `currency` field, add `FxRates` type
- **`backend/app/models/fx_rate.py`** (new) — `FxRate` model, one row per non-CAD currency
  (`USD`, `KRW`), rate expressed as "1 unit = X CAD"
- **`backend/app/services/fx.py`** (new) — `fetch_fx_rates()` (calls `api.frankfurter.dev`),
  `get_cached_rates()` (reads `fx_rates` table)
- **`backend/app/scheduler/jobs.py`** — new daily job `refresh_fx_rates_job`, registered
  alongside existing scheduled jobs
- **`backend/app/api/fx.py`** (new) — `GET /api/fx-rates` — returns cached rates + staleness flag
- **`frontend/src/app/watchlist/page.tsx`** — fetch `/api/fx-rates` once on load, `toCad()`
  helper for header total + sheet-panel secondary display, stale-indicator icon

### Dependencies
- **`process_item` job** (`backend/app/scheduler/jobs.py`) — currency-fill piggybacks on the
  same locked `Product` row read already used for the alert-dedup fix (#48) and name inference
  (#44), no new query.
- **`compute_status`/alert comparison** — unchanged; one-currency-per-product means raw
  `last_price` comparison stays valid, no FX involved.
- **`api.frankfurter.dev`** (was `api.frankfurter.app` — domain migrated 2026-08-20, see
  challenges.md #7a) — free, no API key, ECB-based rates; only 2 pairs ever queried
  (`USD→CAD`, `KRW→CAD`).

### Breaking Changes
None — additive nullable column, additive optional API fields, existing single-currency display
(bare `$`) is the CAD default's exact output.
