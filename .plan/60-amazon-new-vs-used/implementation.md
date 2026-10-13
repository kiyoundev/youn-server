# Issue #60: Implementation

## Steps

### 1. Capture real HTML (Pi)
Browser-DevTools captures of all four page states exist (2026-10-12: `B0GSRYXZM5`, `B0GSS5TK8R`, `B0FQFPN3WR`, `B073S5JHRV`). The remaining check is what the Pi's headless scraper actually receives.
- [x] Capture through the scraper's own browser (local container, throwaway script — since deleted): markers and prices match the browser captures, no captcha/redirect, price present in `page.content()`; ancestor walk verified on the real plain and accordion HTML (see `context.md`)
- [ ] Pi cross-check happens in step 6 through real manual scrapes (no capture script)

### 2. Fixtures and parsers (`patchright_scraper.py`, `tests/scraper/test_amazon.py`)
- [x] Trimmed fixtures as files in `backend/tests/scraper/fixtures/amazon/` (tokens, session ids, postal code removed): `plain_new.html`, `import_fees_new.html` (fifth fixture: international seller, delivery and import-fee amounts next to the price), `accordion_both.html`, `used_only.html`, `no_featured_offer.html`
- [x] `_amazon_new_price(html)`: from `#add-to-cart-button`, walk up to the nearest container (below `body`) holding `.apex-pricetopay-value`, first non-empty `.a-offscreen` → fallback `customerVisiblePrice[amount]` in the button's form → `None`. Reuses the shared `_parse_price` (the selected nodes never carry "with N percent savings"). No `[data-pricetopay-label]`.
- [x] The label-style text `"$52.13 with 5 percent savings"` is never read (test)
- [x] `_amazon_used_price(html)`: first non-empty `#usedBuySection .offer-price`
- [x] Tests (tests/scraper/test_amazon.py, 22 new): plain `88.0`, import-fees `58.7`, accordion `54.98` (also with the used row placed first), used-only: no new price and used `637.19`, no-featured: neither, decoys not read, fallback to form amount, price outside the button's ancestry → `None`, `-ubb` button never counts as new, non-numeric amount → `None`
- [x] Written tests-first (red on missing functions), then implemented; full suite 661 passed. Both parsers are not wired into `get_price` yet (step 3)

### 3. Scraper wiring
- [x] `ScraperResult.used_price` (default `None`)
- [x] `get_price`: one `page.content()` and one parse per attempt (the three parsers accept the shared soup via `_as_soup`, so the 1–2 MB page isn't parsed three times on the Pi)
- [x] `no_new_offer` → `oos` with `used_price` (redirected variant → `oos`, no used price); new price found → `ok` CAD; new buy box but no price → retried, then `error: "price not found in the new buy box"`; no buy box at all (captcha) keeps `"exhausted retries"`
- [x] Removed `_find_price_text` and its page-wide regex fallback; `_run_get_price` now patches only the browser launch and the title read, so `get_price` exercises the real parsers. The title is still read through Playwright (kept by decision)
- [x] Tests: the inline guessed fixtures were replaced by the real ones; `test_patchright.py`'s two Amazon tests now feed the price through `page.content()`. Full suite: 664 passed

### 4. Persistence
- [x] Migration `0020_listing_used_price.py` written (nullable `Float`, like `last_price`)
- [x] Migration `0020` run locally: upgrade 0019 → 0020, `used_price | double precision` (nullable, no default) in `\d watch_items`, downgrade and re-upgrade both clean
- [x] `Listing.used_price`; `process_item` sets it on `oos` (clearing it when that scrape has none), clears it on `ok`, keeps it on `error`
- [x] `test_jobs.py` (4 new): stored on oos without touching `last_price` or `PriceHistory`, stale value cleared by an oos without one, kept through an error, cleared on ok. Written first (3 red), then implemented; full suite 668 passed

### 5. API and UI
- [x] Listing API schema + builder + frontend type: `used_price` (route test helper updated, plus a new test that it reaches the response without affecting status or price; backend 669 passed, `tsc --noEmit` clean)
- [x] Info icon in the retailer row (`watchlist/page.tsx`): `CircleAlert` in the muted gray (`text-muted-foreground`, not the error red), only when `oos` and `used_price !== null`; tooltip `Used available at {CAD price}`. UI check is the user's (not yet done)

### 6. Live verification
- [ ] Apply migration 0020 on the Pi before deploying the code
- [ ] Manual scrape of `B0GSS5TK8R`: status `oos`, `used_price` ≈ `637.19`, no price drop alert, icon visible
- [ ] Manual scrape of `B0GSRYXZM5`: `oos`, no icon
- [ ] An in-stock listing: `ok`, correct new price, `used_price` null

### 7. Cleanup
- [ ] Run `backend/.venv/bin/python -m pytest tests -q`
- [x] Rewrote #60 in `.doc/issues.md` (as-built description, criteria ticked, limitations); added #65 (used offer as a separate listing) and #64 (name/currency/retailer inference on every outcome); index updated. #60's Pi criterion stays open until deployed
