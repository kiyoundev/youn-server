# Issue #64: Context

## Issue Description
Metadata a scrape managed to read (`product_title`, `currency`, `site_name`) is applied only on `ok`. Items that start out of stock (or erroring) stay "Untitled" with no inferred currency. Found live-testing #60: used-only AirPods Max 2 (`B0GSS5TK8R`) reported `oos` correctly but stayed "Untitled".

Full text and acceptance criteria: `.doc/issues.md` Issue #64. Related: #44 (name/retailer inference), #45 (currency inference), #48 (locked Product read), #60 (surfaced it).

**Decision made in planning (deviates from the issue text):** on the generic `_run_hierarchy` path, name and retailer are attached only for `ok`/`oos`. A non-product error page (404, login wall, unrecognised block) has a `<title>` and name inference is first-write-wins, so it would become the permanent name. `_detect_bot_block` covers only two signatures. Currency stays attached on errors (harmless, host-derived). Dedicated scrapers (Amazon/IKEA/Uniqlo) still attach on errors since they only do so after parsing a real product response.

## Component / Route Summary

### Current State
- `process_item` (`backend/app/scheduler/jobs.py:154`): retailer fill (280-287, before the locked read), name fill (309) and currency fill (318) (after the locked read at 299). All in the `ok` path. `oos` (201-220), `error` (222-228) and the anomalous "ok with no price" (230-243) branches commit and return before them.
- `AmazonCAScraper.get_price` (`patchright_scraper.py:351`): title via Playwright `_find_product_title(page)` only when `price is not None`; `oos` result has currency only; errors carry nothing.
- `IKEAScraper` (`ikea_scraper.py:33`): currency on `ok`/`oos`; never a name; error results bare.
- `UniqloScraper` (`uniqlo_scraper.py:41`): currency + title on `ok`/`oos`; error results bare.
- `_run_hierarchy` (`base.py:818-842`): `dataclasses.replace` attaches site_name/title/currency to every result, including `_detect_bot_block` errors.

### Target State
- One helper in `jobs.py` applies the three guarded fills; called from every branch.
- Amazon reads `#productTitle` from the already-parsed soup on every attempt.
- IKEA/Uniqlo attach parsed metadata on every outcome past parsing.
- `_run_hierarchy` withholds name/retailer on `error`, and everything on a detected bot block.

## Impact & Risk

### Files Changed
- **`backend/app/scheduler/jobs.py`** — extract `_apply_scrape_metadata`; call from ok/oos/error/anomalous-ok branches.
- **`backend/app/services/scraper/patchright_scraper.py`** — soup-based title helper; drop `_find_product_title`; attach on ok/oos/named error.
- **`backend/app/services/scraper/ikea_scraper.py`** — attach name (if payload has one) and currency on error results after parse.
- **`backend/app/services/scraper/uniqlo_scraper.py`** — attach title/currency on post-parse error results.
- **`backend/app/services/scraper/base.py`** — `_run_hierarchy` metadata gating.
- **`backend/tests/scheduler/test_jobs.py`**, **`tests/scraper/test_amazon.py`**, **`test_ikea.py`**, **`test_uniqlo.py`**, **`test_base.py`** — new cases.
- **`backend/tests/scraper/fixtures/amazon/`** — possibly a captcha/robot-check fixture.

### Dependencies
- **`RETAILER_DISPLAY_NAMES`, `_derive_retailer`, `_strip_tld_suffix`, `_hostname_of`** — reused unchanged by the retailer guard.
- **#48 locked Product read** — must stay on the `ok` path.

### Breaking Changes
None. No schema or API change; existing "Untitled" products self-heal on their next scrape (name still NULL).
