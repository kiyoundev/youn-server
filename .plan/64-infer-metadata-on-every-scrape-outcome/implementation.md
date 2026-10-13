# Issue #64: Implementation

## Steps

### 1. `process_item` helper (jobs.py)
- [x] Add `_apply_scrape_metadata(listing, product, scrape)` — retailer guard (hostname not in `RETAILER_DISPLAY_NAMES` and `listing.retailer == _derive_retailer(hostname)` → `_strip_tld_suffix(site_name)`), name only if `product.name is None`, currency only if `product.currency is None`. Guards copied verbatim.
- [x] `ok` path: replace the three inline fills with one call after the locked Product read (retailer fill moves below the lock; same transaction, no behaviour change).
- [x] `oos`, `error`, and anomalous "ok with no price" branches: plain `await session.get(Product, listing.product_id)` then helper, before commit. Comment why plain `get` is safe here (return before any locked read; #48 trap) and that `ok` must keep the locked read.

### 2. Amazon
- [x] Add `_amazon_product_title(soup)` — `#productTitle` text, stripped, `None` if absent.
- [x] Remove `_find_product_title` (Playwright round trip) and its `PRICE_LOCATOR_TIMEOUT_MS` use if otherwise unused.
- [x] Per attempt: `title = None if variant_gone else _amazon_product_title(soup)` — a captcha page has no `#productTitle`, so None.
- [x] Attach `product_title`+`currency="CAD"` on `ok` and `oos`. On the named error ("price not found in the new buy box") record `failure_title` alongside `failure_reason` and return `error` with title+currency.
- [x] Leave other error paths bare (exhausted retries, launch failure, variant_gone with nothing else).

### 3. IKEA / Uniqlo
- [x] Live-fetch the IKEA fragment endpoint for a real item; check whether the payload exposes a name. If yes, attach `product_title` on ok/oos; if no, stay currency-only and note it in `.doc/issues.md`.
- [x] IKEA: error results raised after `product` parsed carry currency (and name).
- [x] Uniqlo: post-parse errors (`variant not found`, `no stock or price data`, shape errors where title exists) carry `title`; currency when parsed.

### 4. Generic path gating (base.py `_run_hierarchy`)
- [x] If `result.status == "error"`: attach `currency` only (no name, no site_name).
- [x] If error reason came from `_detect_bot_block`: attach nothing.

### 5. Tests
- [x] `test_jobs.py`: oos fills name/currency/retailer; error fills; existing name/currency not overwritten; manual retailer edit survives; curated-host retailer untouched; `ok` still takes the locked read (existing #48 test stays green).
- [x] `test_amazon.py`: title+CAD on ok / used-only oos (`used_only.html`) / named error; none for redirected variant; none for a captcha fixture. Assert no Playwright title call.
- [x] `test_ikea.py`, `test_uniqlo.py`: metadata per status.
- [x] `test_base.py`: bot-block page → no metadata; 404-style error → currency only; oos → full metadata.

### 6. Validation
- [x] Full backend test run green (689 passed).
- [ ] Live: add `B0GSS5TK8R`; name "Apple AirPods Max 2 - Purple", currency CAD, status `oos`.
- [ ] Live: an existing "Untitled" oos product gets named on next scrape.

### 7. Cleanup
- [x] Remove dead code/imports; update `.doc/issues.md` #64 criteria for the generic-path gating decision.
