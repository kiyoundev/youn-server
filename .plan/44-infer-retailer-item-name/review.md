# Issue #44: Review

## AI Review
_Run via `/code-reviewer:review` on staged changes, 2026-08-19._

### Summary
Adds name/site inference from scraped page metadata: `ScraperResult` gains `site_name`/`product_title` fields populated by a new independent extraction pass in `BaseScraper._run_hierarchy` (og tags → JSON-LD → `<title>` heuristic) plus a dedicated Amazon-specific title read; `process_item` fills `Listing.retailer`/`Product.name` with guards against overwriting user edits; `Product.name` becomes nullable end-to-end (migration, schema, frontend). Well-scoped, the guard logic is sound, and the frontend fallout (multiple render sites, a real crash risk in the search filter, a TS type error) was caught proactively rather than left for a bug report. One real gap and a couple of legitimate efficiency notes below — nothing blocking.

### Critical
None found.

### Major — ✅ fixed
- **`ProductUpdate.name` wasn't updated to match `ProductCreate`'s empty-string-to-`None` coercion — a real, untested gap.** `ProductCreate.name`'s validator explicitly coerced `""` → `None`, but `ProductUpdate` still used the old plain `_strip_name = field_validator("name")(strip_whitespace)`, which left `""` as `""`. A direct `PATCH /api/items/{id}` with `{"name": ""}` would set `product.name = ""`, not `NULL` — permanently defeating `process_item`'s `is None` inference guard and the frontend's `?? "Untitled"` fallback (only catches `null`/`undefined`, not `""`).
  **Fix:** factored the coercion into a shared `strip_name_or_none` validator (`schemas/validators.py`), used by both `ProductCreate.name` and `ProductUpdate.name` now — one place, not two call sites that can drift again. Added `test_product_update_empty_name_coerces_to_none` to close the test gap the review flagged (confirmed no prior test exercised this).

### Minor — ✅ fixed
- JSON-LD `<script>` tags were getting `json.loads`'d up to 3 times per scrape (`_extract_jsonld`, `_extract_site_name`, `_extract_product_title` each independently re-parsing every script tag). **Fix:** added `_parse_jsonld_scripts(soup)`, parsed once in `_run_hierarchy` and threaded through all three consumers via an optional `jsonld_scripts` param (defaults to `None` → parses on demand, so standalone/test calls to any one function unchanged).
- `AmazonCAScraper.get_price`'s retry loop called `_find_product_title` unconditionally on every attempt, including failed ones whose result was discarded. **Fix:** moved the title fetch inside the same `try` block, now conditional on `price is not None` — only runs on the attempt that's actually going to succeed, while `page` is still open.
- JSON-LD `name` values weren't type-checked before `str(...)` coercion — malformed/adversarial JSON-LD (e.g. `"name"` as a nested object) could coerce to a garbage display string. **Fix:** both `_extract_site_name`/`_extract_product_title` now check `isinstance(name, str) and name` before trusting it, folded into the same edit that fixed the triple-parse.

**Verified:** full backend suite — 339 passed (338 + the new `ProductUpdate` coercion test). Frontend `tsc --noEmit` — clean.

### Praise (from the review, worth keeping in mind)
- The retailer-overwrite guard (`listing.retailer == _derive_retailer(hostname)`) is the right amount of mechanism — no new column, no boolean flag, self-documenting at the call site.
- The `_derive_retailer`/`_hostname_of` import-cycle relocation was planned before writing `process_item`'s fill logic, not discovered mid-implementation.
- Real frontend fallout found beyond the original plan scope — the search filter's unconditional `product.name.toLowerCase()` was a genuine crash waiting for the first `null`-named product, caught by reading the file, not just satisfying the type checker.
- `_split_title`'s conservatism (return `None` on any ambiguity) is the right call for a heuristic feeding a persisted DB value; test suite explicitly covers the ambiguous-multiple-separator case.
- Guard test coverage is genuinely bidirectional (fills when untouched, doesn't overwrite when edited) for both `retailer` and `product.name`, not just the happy path.

### Verdict
**Approve.** All findings (1 Major, 3 Minor) fixed and verified — full suite green.

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
