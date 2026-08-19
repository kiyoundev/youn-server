# Issue #44: Context

## Issue Description
Full text: `.doc/issues.md#L2443-2484`.

Today, two display values fall back to raw, unpolished derivations instead of anything scraped from the actual page:
1. **Retailer badge** — `RETAILER_DISPLAY_NAMES` (`services/scraper/router.py`) is a small hand-curated dict (currently just `"amazon.ca": "Amazon"`); every other hostname falls through to `hostname.replace(".", "_")` (e.g. `muddygeorge_com`), a raw fallback rather than a real brand name.
2. **Product name** — `ProductCreate.name` is required today; no path for it to be inferred from the page when left blank.

Both trace back to the same missing capability: `ScraperResult` never captures anything about the scraped page's title/site name/brand.

**Scope clarified during grilling** (see `_index.md`'s success criteria for the refined ACs): the issue's own text described one new `ScraperResult.site_name` field intended to cover both gaps — grilling surfaced that site identity ("Muddy George") and a specific product's title ("Cayl Cap Black") are different signals from different parts of a page, so this plan splits them into two fields (`site_name`, `product_title`) rather than conflating them into one.

## Component / Route Summary

### Current State
- `ScraperResult` (`services/scraper/result.py`): bare — `price: float | None`, `status: Literal["ok", "oos", "error"]`. Nothing about page title/site name/brand.
- `BaseScraper._run_hierarchy` (`services/scraper/base.py`): tries 4 price-extraction methods in order (Shopify JSON API → JSON-LD → OG meta → Next.js `__NEXT_DATA__`), returns the first successful `ScraperResult`, short-circuiting on success. `_extract_shopify` never builds a `BeautifulSoup` object (fetches a separate JSON API instead); the other three all parse `soup` from the already-fetched `html`.
- `AmazonCAScraper.get_price` (`services/scraper/patchright_scraper.py`): bypasses `_run_hierarchy`/`BaseScraper` entirely — custom Playwright locator/regex price extraction (`_find_price_text`), constructs its own `ScraperResult` directly. Never touches `soup` or any of `BaseScraper`'s extraction methods.
- `_derive_retailer(hostname)` (`api/items.py`): `RETAILER_DISPLAY_NAMES.get(hostname, hostname.replace(".", "_"))`. Called once, synchronously, at listing **creation** time (before any scrape) via `_resolve_retailer_and_scraper_type` — sets `Listing.retailer` immediately, a plain `NOT NULL` string column. Also user-editable later via `PATCH .../listings/{id}`'s `retailer` override field.
- `Product.name`: `Mapped[str]`, `NOT NULL`, no default. `ProductCreate.name: str` — always required today.
- `process_item` (`scheduler/jobs.py`): the single function both `#41`'s add-time dispatch and every scheduled `poll_prices` cycle funnel every scrape through. Loads `listing` early; loads `product` late (via a `with_for_update()` locked read, added for `#48`'s alert-dedup race fix) — only once it needs to check/write `product.alerted_at`.
- Frontend (`watchlist/page.tsx`): renders `listing.retailer` directly at ~5 spots (badge span, chart legend, open-link/edit-URL/remove-button aria-labels). Bulk-add failure toast: `failed.map((f) => \`${f.url} (${f.detail})\`).join(", ")` — raw URL, unreadably long for a real product URL. `ListingFailure` schema currently only has `url`/`detail`, no retailer field.

### Target State
- `ScraperResult` gains `site_name: str | None` and `product_title: str | None`, both defaulting to `None`.
- `BaseScraper._run_hierarchy` parses `soup` once, unconditionally (even on the Shopify success path, which doesn't otherwise need it), and runs one independent name-extraction pass (`og:site_name`/`og:title` meta → JSON-LD `Organization`/`Brand`/`Product.name` → `<title>` tag heuristic → `None`) attached to whichever `ScraperResult` the price hierarchy ends up returning, regardless of which of the 4 price methods won.
- `AmazonCAScraper.get_price` gets its own small title extraction (e.g. `page.title()` or an Amazon-specific DOM selector) added alongside its existing price extraction, populating `product_title` on its own `ScraperResult` construction.
- `process_item`: right after a successful scrape (`scrape.status == "ok"`, price found), if `scrape.site_name` is present and `listing.retailer` still equals `_derive_retailer(hostname)` (i.e. untouched since creation — the guard against stomping a manual edit), overwrite `listing.retailer = scrape.site_name`. Later, at the existing locked `product` read (added for `#48`), if `scrape.product_title` is present and `product.name is None`, fill `product.name = scrape.product_title`.
- `Product.name` becomes `Mapped[str | None]`, nullable (migration). `ProductCreate.name: str | None = None`.
- `ListingFailure` schema gains a `retailer` field (or reuses hostname-derivation inline) — `create_item`'s failure-collection path calls `_derive_retailer(hostname)` for each failed URL (no scrape involved, synchronous, same fallback logic as today's creation-time derivation).
- Frontend: `watchlist/page.tsx`'s bulk-add failure toast renders each failure's retailer name instead of the raw URL; product name rendering gets a fallback label (e.g. "Untitled") for the `NULL` case, however briefly it's visible before the first scrape completes.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/result.py`** — `ScraperResult` gains `site_name`, `product_title`.
- **`backend/app/services/scraper/base.py`** — `_run_hierarchy` restructured to always parse `soup` and run the independent name-extraction pass.
- **`backend/app/services/scraper/patchright_scraper.py`** — `AmazonCAScraper.get_price` gains title extraction.
- **`backend/app/scheduler/jobs.py`** — `process_item` fills `listing.retailer`/`product.name` with guards, at two points in the function.
- **`backend/app/models/product.py`** + new Alembic migration — `name` becomes nullable.
- **`backend/app/schemas/product.py`** — `ProductCreate.name` optional; `ListingFailure` gains `retailer`.
- **`backend/app/api/items.py`** — `create_item`'s failure-collection path derives and attaches `retailer` to each `ListingFailure`.
- **`frontend/src/lib/api/items.ts`** — `Product.name: string | null`; `ListingFailure` type gains `retailer`.
- **`frontend/src/app/watchlist/page.tsx`** — `NULL`-name fallback label; failure toast uses `retailer` instead of raw `url`.

### Dependencies
- **`#48`'s `process_item` locked `Product` read** — this issue reuses it (piggybacks the `product.name` fill on the same `with_for_update()` read already there for the alert-dedup fix), rather than adding a second query.
- **`#41`'s add-time dispatch / `poll_prices`** — both already funnel every scrape through `process_item`; no new dispatch path needed, the fill logic lands once, in the one place both callers already share.
- **`_derive_retailer`/`RETAILER_DISPLAY_NAMES`** (`api/items.py`, `services/scraper/router.py`) — reused as-is for both the retailer-fill guard (Q3) and the bulk-add failure toast fix; no changes to this existing logic.

### Breaking Changes
- `ProductResponse.name` (and the frontend `Product.name` type) becomes `string | null` — any consumer assuming it's always a non-empty string needs updating. Only internal consumer is `watchlist/page.tsx`, updated as part of this issue.
- `products.name` migration: existing rows are unaffected (already non-null), only the constraint relaxes — no data migration/backfill needed, purely additive.
