# Issue #58: Implementation

## Steps

### 1. Pre-flight verification (before writing code)
- [x] API reachable from the Mac with `x-fr-clientid: uq.ca.web-spa` — in-stock and sold-out variants both read correctly (planning session)
- [x] API reachable from the Pi — returns `{"status":"ok", ...}` (planning session)
- [x] `_resolve_final_url` on a Uniqlo URL from the Pi — HEAD returns 200, so the add flow's URL resolution works and no change to `items.py` is needed (see `challenges.md`)

### 2. Config
- [x] `scraper/config.py` — add `UNIQLO_CLIENT_IDS = {"ca": "uq.ca.web-spa"}` with a comment on where the value comes from (the site's public `main-*.js` bundle) and that it is region-specific

### 3. Scraper
- [x] `scraper/uniqlo_scraper.py` — `UniqloScraper(BaseScraper)`, structured like `IKEAScraper`:
  - parse region, language, product ID and price group from the URL path with a regex matched on the path only (never the raw URL); `colorDisplayCode` / `sizeDisplayCode` via `parse_qs`
  - unsupported region / missing product ID → specific `error` results
  - one `httpx` GET with `_build_headers`, the client-ID header and the API query; non-200 or `status != "ok"` → `error` carrying the API's message
  - choose the variant per `schema.md` (exact, color-only, whole product); not found → `error`
  - map stock and price to `ScraperResult` (`oos` keeps its price; promo else base; currency from the API)
  - catch everything else → `error` via `_describe_exception`, with `_log.warning(..., exc_info=True)` like `IKEAScraper`
- [x] `router.py` — import `UniqloScraper`, add `"uniqlo.com": UniqloScraper` to `RETAILER_MAP`

### 4. Tests (`tests/scraper/test_uniqlo.py`)
Fixtures trimmed from the two real API responses captured during planning (E491096-000 in stock at $79.90; E488599-000 sold out at $59.90), inlined as constants like `test_amazon.py` does, with `respx` for the request.
- [x] URL parsing: path variants, query params, missing price group defaults to `00`, region/language extraction, no product ID
- [x] Exact variant in stock → `ok` + price + CAD; the request carries `x-fr-clientid`
- [x] Exact variant sold out → `oos` with price kept
- [x] Promo price wins over base when present
- [x] No color/size: first in-stock variant's price; all sold out → `oos`
- [x] Color only: restricted to that color
- [x] Variant not in `l2s` → `error` with the variant in the reason
- [x] Region `us` → `error` `unsupported Uniqlo region`
- [x] API error body (`invalid or missing client id`) and HTTP 400/500 → `error` carrying the message
- [x] Network exception → `error`
- [x] `RETAILER_MAP` routes `uniqlo.com` (and `www.uniqlo.com` via `_hostname_of`) to `UniqloScraper`

### 5. Live verification (on the Pi, after deploy)
- [ ] Add the blouson URL (color 67 / size 004) → `ok`, $79.90, retailer "Uniqlo"
- [ ] Add the sold-out example (E488599-000, color 38 / size 003) → Out of Stock
- [ ] Add a bare product URL with no variant → priced at the first in-stock variant
- [ ] A `/us/` URL → fails with `unsupported Uniqlo region 'us'` in the tooltip
- [ ] Delete the leftover empty "Uniqlo Fleece Lined Stand Blouson" product, or add the listing to it with the "+" button

### 6. Docs and cleanup
- [ ] `.doc/issues.md` #58 — write the root cause and findings (from `context.md`), tick the acceptance criteria, note that the approach depends on an undocumented API
- [ ] Run `backend/.venv/bin/python -m pytest tests/scraper tests/api -q`
- [ ] No debug logs or scratch files left in the repo (probe captures live only in the session scratchpad)
