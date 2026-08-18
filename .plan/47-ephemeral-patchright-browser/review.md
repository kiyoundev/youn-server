# #47: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

### Summary
Replaces `PatchrightScraper`'s daily-recycle lifecycle with a close-on-idle model: both `poll_prices` (end-of-cycle) and a new per-request `_dispatch_first_scrapes()` (end-of-batch) call a new `close_if_idle()` that tears down the browser only when the global `_active_scrapes` counter is back to 0. Solid, well-tested refactor overall — one real concurrency gap in `close_if_idle()` itself needed fixing.

**Verdict**: Request Changes → **Fixed**, see below.

### Critical Issues (Must Fix)
None.

### Major Issues (Should Fix)

**1. `patchright_scraper.py` — `close_if_idle()` dropped the `_start_lock` guard `recycle_browser()` used to have, opening a double-close race between the two independent callers**
- **Current** (before fix):
  ```python
  async def close_if_idle(cls) -> None:
      if cls._active_scrapes == 0:
          await cls.close_browser()
  ```
- **Impact**: `poll_prices` and `_dispatch_first_scrapes` are two *independent* callers that can both legitimately be "the last one out" at nearly the same moment. Both pass the `_active_scrapes == 0` check, and both call `close_browser()`. `close_browser()`'s own guard (`if cls._context: await cls._context.close()`) isn't enough — the check and the `_context = None` reset are on opposite sides of a real `await` (`_context.close()`), so a second caller can read `cls._context` as still truthy and call `.close()` on it a second time before the first caller ever nulls it out. A double-`close()` can raise, and neither call site wraps `close_if_idle()` in a try/except.
- **Root cause**: the old `recycle_browser()` was the *sole* closer and wrapped its whole check-and-close sequence in `_start_lock`, making it atomic against other callers. This refactor introduced a second independent closer (`_dispatch_first_scrapes`) without carrying that lock over to the shared `close_if_idle()`.
- **Status**: ✅ **Fixed** — `close_if_idle()` now acquires `_start_lock` around the check-and-close sequence, same as `recycle_browser()` used to, so the two callers' close attempts serialize instead of overlapping.

### Minor Issues (Nice to Have)
1. Diff hygiene: several unrelated lines were reformatted/collapsed by what looks like an editor auto-format-on-save (e.g. `main.py`'s `session.execute(...)`, `jobs.py`'s log calls, `patchright_scraper.py`'s `wait_for_function`/`text_content`/`goto` calls, blank-line-before-import removal in test files). Cosmetic only, restored where practical.
2. `items.py`'s `if product.listings:` guard before spawning `_dispatch_first_scrapes` in `create_item` is a harmless no-op-avoidance (the old per-listing loop was already a no-op on an empty list); not a bug.

### Praise
- `close_if_idle()`'s docstring clearly explains *why* it checks the global counter instead of a per-caller local one, and cites both call sites by name.
- `_dispatch_first_scrapes()` (one `spawn()` per request, grouped `gather()`, no debounce timer) cleanly removes an entire class of "maybe one more is coming" timing logic by construction.
- Tests assert *ordering* via a shared `call_order` list (`test_poll_prices_closes_browser_once_after_full_cycle`, `test_dispatch_first_scrapes_closes_browser_once_batch_drains`), not just call counts — this actually catches a regression to "closes mid-cycle" or "closes before the batch drains."
- `test_dispatch_first_scrapes_does_not_close_when_other_scrape_still_in_flight` manipulates the real `PatchrightScraper._active_scrapes` global (with try/finally cleanup) instead of over-mocking — the right fidelity for a global-counter-based design.
- `close_if_idle()` is correctly invoked *inside* `poll_prices`'s existing `_prices_lock` block, before release — matches the plan's stated rationale and is verified by a dedicated test.

### Test Coverage Assessment
- [x] Happy path (both callers, close-on-drain)
- [x] "Don't close while something else is using it" (both callers)
- [x] Regression coverage for `#40`'s concurrent-launch-sharing guarantee (untouched, still passing)
- [x] Concurrent-double-close race — added `test_close_if_idle_serializes_concurrent_callers_against_double_close` (`tests/scraper/test_patchright.py`): 5 concurrent `close_if_idle()` callers against a `close_browser()` mock with an artificial `asyncio.sleep(0.01)` mid-call to widen the race window, asserting exactly one actual close happens. Verified this test fails (5 awaits instead of 1) against the pre-fix implementation before confirming it passes with the `_start_lock` fix.

---

## Live Verification (local dev, `docker-compose.local.yml`)

Performed against a rebuilt `backend` container with temporary `LIVE-VERIFY` diagnostic logging in `start_browser()`, `close_browser()`, `close_if_idle()`, and `_dispatch_first_scrapes()` (removed afterward — see Cleanup below). Real `amazon.ca` product URLs were used since `amazon.ca` is hardcoded in `RETAILER_MAP` to always route through `AmazonCAScraper`/`PatchrightScraper`, guaranteeing a real Chromium launch rather than depending on HTTPScraper failing first.

### Test 1 — real launch → real scrape → real close
Added a listing (`Live-Verify A`, AirPods Max). Log sequence:
```
LIVE-VERIFY _dispatch_first_scrapes: starting batch [9]
LIVE-VERIFY start_browser: launched, context id=281472476283904
LIVE-VERIFY _dispatch_first_scrapes: batch [9] drained, checking close_if_idle
LIVE-VERIFY close_browser: closing context id=281472476283904
```
Resulting listing: `status: watching`, `last_price: 581.49`. Confirms a real launch, a real successful scrape, and a real close once idle.

### Test 2 — relaunch after close produces a genuinely new context + real price
Added a second listing (`Live-Verify B`, different ASIN) right after Test 1's close:
```
LIVE-VERIFY start_browser: launched, context id=281472482995568
```
`281472482995568 != 281472476283904` — a real teardown/relaunch, not a silent no-op. Resulting listing: `status: watching`, `last_price: 209.0016`, `last_scrape_status: ok`.

### Test 3 — poll_prices vs. an ad-hoc add genuinely overlapping
A `poll_prices` restart-triggered run (fires automatically on app startup via `next_run_time=datetime.now(_TZ)`) and a manually-triggered `POST /api/poll/prices` were each caught overlapping with a concurrent ad-hoc `POST /api/items` add on the same event loop. Timestamped log excerpt from the second, cleaner overlap:
```
16:11:40.966  _dispatch_first_scrapes: starting batch [12]
16:11:42.314  start_browser: launched, context id=281472202702032
16:11:44.717  _dispatch_first_scrapes: batch [12] drained, checking close_if_idle
16:11:44.718  close_if_idle: active_scrapes=1 context=281472202702032   <- correctly skipped, poll_prices still using it
16:11:53.744  close_if_idle: active_scrapes=0 context=281472202702032   <- poll_prices finished; only now closes
16:11:53.744  close_browser: closing context id=281472202702032
```
Cross-checked against `price_history`: the concurrent `poll_prices` cycle scraped listings 3, 7, 9, 10, 11 across `16:11:39`–`16:11:51`, overlapping exactly with the ad-hoc batch's `16:11:40`–`16:11:53` window. Confirms `close_if_idle()`'s global-counter check works correctly under real, non-contrived concurrency: whichever caller finishes first defers, whichever finishes last does the actual close — and only one browser context was launched for the whole overlapping window (no regression to `#40`'s single-launch guarantee).

### Cleanup performed
- Removed all `LIVE-VERIFY` diagnostic logging from `patchright_scraper.py` and `items.py`.
- Deleted the 4 test products (`Live-Verify A`–`D`, ids 9–12) from the local dev DB via `DELETE /api/items/{id}`; confirmed only the original 3 listings remain.
- Rebuilt and restarted the `backend` container with the clean code; confirmed it starts healthy.
- Also fixed an unrelated pre-existing `ruff` E402 warning in `patchright_scraper.py` (module-level `_log = logging.getLogger(__name__)` sitting between two import blocks) surfaced by IDE lint feedback mid-session — moved below the imports, `ruff check` now passes clean on that file.

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
