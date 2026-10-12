# Issue #58: Context

## Issue Description
Uniqlo listings don't scrape. None of the extraction strategies we have (JSON-LD, OpenGraph, Shopify, `__NEXT_DATA__`, RSC flight, the generic hierarchy) work on them. Diagnose first, then fix — either a dedicated scraper in `RETAILER_MAP`, a selector/wait entry, or a documented won't-fix.

**Acceptance criteria (from `.doc/issues.md` #58):**
- Root cause identified and written into the issue, with evidence
- A real Uniqlo listing scrapes to the correct price, live-verified (or a documented won't-fix)
- If a fix ships: regression fixture and test in `tests/scraper/`
- A failure still surfaces a specific `last_scrape_error`, not the generic "no price found on page"

**Added during planning:**
- The user tracks a specific variant via the URL (`?colorDisplayCode=67&sizeDisplayCode=004`). A sold-out variant must show Out of Stock.
- Canada only (`/ca/`), by decision.

## Diagnosis (done during planning, 2026-10-11)

Test URL: `https://www.uniqlo.com/ca/en/products/E491096-000/00?colorDisplayCode=67&sizeDisplayCode=004` (Zip Up Blouson, Blue, M).

| Finding | Evidence |
|---|---|
| **Not a bot-block** | Plain HTTP GET returned 200, a 1 MB page, from the Mac. The Pi also gets a normal `{"status":"ok"}` from the API. |
| **Client-rendered SPA** | `<title>` is the generic "UNIQLO home"; no JSON-LD, no `og:price`, no `__NEXT_DATA__`, no RSC chunks — which is why every extractor misses and the add fails. |
| **Price is in an inline Redux blob** | `window.__PRELOADED_STATE__` → `entity.pdpEntity["E491096-000-00"].product.prices` = `{base: {value: 79.9, currency CAD}, promo: null}`. No stock in it (`l2Entity` is empty). |
| **Stock and per-variant price come from Uniqlo's commerce API** | The site's own JS calls `GET /ca/api/commerce/v5/en/products/{id}/price-groups/{pg}/l2s?withPrices=true&withStocks=true…` with header `x-fr-clientid: uq.ca.web-spa` (read from the public `main-*.js` bundle). One response covers every color/size. |
| **API verified** | In stock: color 67 / size 004 → `IN_STOCK`, quantity 11, $79.90. Sold out: E488599-000, color 38 / size 003 → `STOCK_OUT`, quantity 0, $59.90. |
| **The empty "Uniqlo Fleece Lined Stand Blouson" row** | A product with no listings. `create_product` in `items.py` always commits the product, even when every URL fails the probe; the failure goes only into the response's `failed` list. So there was no listing/`last_scrape_error` to read. |

The API is Uniqlo's internal one (no public documentation found); see `challenges.md`.

## Component / Route Summary

### Current State
- `RETAILER_MAP` (`router.py`) maps `amazon.ca` → `AmazonCAScraper`, `ikea.com` → `IKEAScraper`. Anything else goes through `detect_scraper_type`: `HTTPScraper` then `PatchrightScraper`, both of which run `_run_hierarchy` and report "no price found on page" for Uniqlo.
- `IKEAScraper` is the template for a dedicated, browser-free scraper: parse the URL, one `httpx` call, map the JSON to `ScraperResult`, return `oos` with a kept price, specific `error_reason` on every failure.
- `_resolve_retailer_and_scraper_type` skips `detect_scraper_type` for hosts in `RETAILER_MAP` and returns `scraper_type=None`.

### Target State
- New `UniqloScraper` in `backend/app/services/scraper/uniqlo_scraper.py`, registered as `"uniqlo.com": UniqloScraper`.
- Region→client-ID table in `scraper/config.py`, starting with `{"ca": "uq.ca.web-spa"}`.
- Variant selection and stock/price mapping as in `schema.md`.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/uniqlo_scraper.py`** (new) — the scraper.
- **`backend/app/services/scraper/router.py`** — import and register `uniqlo.com`.
- **`backend/app/services/scraper/config.py`** — `UNIQLO_CLIENT_IDS`.
- **`backend/tests/scraper/test_uniqlo.py`** (new) — tests with trimmed real responses.
- **`.doc/issues.md`** — #58: root cause, findings, ticked criteria.

### Dependencies
- **`httpx`, `_build_headers`, `USER_AGENTS`, `_describe_exception`** (`scraper/base.py`) — same request plumbing `IKEAScraper` uses.
- **`_resolve_final_url`** (`api/items.py`) — still runs for Uniqlo URLs on add (HEAD, then GET); must be verified to succeed on a Uniqlo page from the Pi.
- **`_derive_retailer("uniqlo.com")`** — yields `"Uniqlo"`, no display-name entry needed.

### New Dependencies
None.

### Breaking Changes
None. Uniqlo listings already failed; no other host is routed differently.
