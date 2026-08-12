# Issue #3: Challenges & Notes

## Potential Challenges

1. **Amazon CDP fingerprinting** — Amazon's bot detection operates at the CDP level. `patchright` patches these signals at the protocol layer. If `AmazonCAScraper` starts returning `status="error"` consistently in production, the most likely fix is updating `patchright` or rotating the UA string, not rewriting the scraper.

2. **ARM64 Chromium path (Option B)** — Skip `patchright install chromium`; pass `executable_path` directly. Faster build and first launch — no install bookkeeping. Resolve the versioned path at build time with a shell glob:
   ```dockerfile
   RUN CHROMIUM_PATH=$(find /ms-playwright -name "chrome" -type f | head -1) && \
       echo "CHROMIUM_PATH=$CHROMIUM_PATH" >> /etc/environment
   ```
   Read `os.environ["CHROMIUM_PATH"]` in `PatchrightScraper.start_browser()`. When bumping the base image, verify the glob still resolves — the path changes when the bundled Chromium version changes.

3. **Shared browser lifecycle** — `PatchrightScraper._browser` is a class-level singleton. The scheduler job (Issue #6) must call `await PatchrightScraper.start_browser()` before the poll loop and `await PatchrightScraper.close_browser()` in a `finally` block after. If the job exits abnormally without `finally`, the browser process leaks.

4. **`_extract_nextdata()` heuristic false positives** — Recursive search for a numeric "price" key may match shipping cost, tax, or a price for a different product (e.g., a recommended item). If this happens for a known store, add an explicit path to `NEXTDATA_PATHS` as an override. Start the dict empty; populate reactively.

5. **`_extract_shopify()` handle extraction** — Shopify URL shapes vary: `/products/handle`, `/en/products/handle`, `/collections/sale/products/handle`. Use `path.rstrip("/").split("/")[-1]` and strip `.html` suffix. Covers all known shapes but may need updating for unusual storefronts.

6. **Schema.org multi-offer pages** — Some pages have multiple `<script type="application/ld+json">` blocks or nested `offers` arrays (e.g., product with multiple sellers). `_extract_jsonld()` should pick the first `Offer` with a numeric price and check `InStock` availability. Avoid picking `AggregateOffer` (which has `lowPrice`/`highPrice` instead of `price`).

7. **`_parse_price` locale edge cases** — European-locale prices use `.` as thousand separator and `,` as decimal (`"1.299,99"`). Heuristic: if both `,` and `.` present, whichever comes last is the decimal separator. Test against known inputs before shipping.

8. **Costco.ca — effectively unsupported** — Costco has two independent blockers: bot detection (solvable with Patchright) and member-only pricing (login-gated). Prices are not visible without an active session, so no scraper can extract them without stored credentials. Don't add `costco.ca` to a watchlist — it will always return `status="error"`.

9. **BS4 parser choice** — Using `html.parser` (stdlib) not `lxml`. `lxml` is faster but requires a C compile on ARM64 that occasionally fails in the Playwright Docker base image. Not worth the risk at 6h poll intervals.

## Key Differences

| Aspect | Original Plan | Revised Design |
|--------|--------------|----------------|
| Class count | 6 (BaseScraper + 4 concrete + router) | 4 (BaseScraper + HTTPScraper + PatchrightScraper + AmazonCAScraper + router) |
| Site support | Explicit per-retailer config required | Any URL auto-supported via extraction hierarchy |
| `SELECTORS` dict | 4 keys (amazon, bestbuy, walmart, generic) | Removed — Amazon selectors are class constants on `AmazonCAScraper` |
| `RETAILER_MAP` | 4+ entries | 1 entry (amazon.ca) |
| Return type | `float \| None` | `ScraperResult(price, status)` |
| OOS handling | Indistinguishable from error | `status="oos"` — distinct from `status="error"` |
| Patchright usage | Amazon only, pre-routed | Fallback for any JS-rendered URL |
