# #47: Context

## Issue Description

`#40` made `PatchrightScraper`'s browser launch lazily (on first real use, guarded by `_start_lock`) but keep running indefinitely afterward — torn down only by a daily `recycle_browser()` scheduler job or real app shutdown. That persistent-with-recycle model exists to bound the staleness/memory-creep risk of a genuinely long-running process. Re-examined this session while planning `#15` (which adds Xvfb underneath Patchright, and would need to build on top of whatever lifecycle model wins here): this app's actual Patchright traffic is sparse — a handful of `poll_prices` listings every 6h, plus occasional `#41` ad-hoc adds — so the browser mostly sits idle, paying a continuous ~100–250MB RAM cost on a Pi 4B shared with every other service, for no real latency benefit at this request volume.

Fix: close the browser once nothing needs it, instead of leaving it open until a scheduled recycle. Direct consequence: `recycle_browser()` and its daily job become unnecessary and should be removed — they exist purely to manage a long-running process's risk, and nothing will run long enough to need managing.

Full acceptance criteria: see `.doc/issues.md` → Issue #47.

## Component / Route Summary

### Current State
- `PatchrightScraper._context`/`_playwright` launch lazily via `start_browser()` (double-checked locking on `_start_lock`), stay set indefinitely once launched.
- `PatchrightScraper._active_scrapes: int` already correctly tracks in-flight usage — incremented before `new_page()`, decremented after `page.close()`, in both `PatchrightScraper.get_price()` and `AmazonCAScraper`'s override (`patchright_scraper.py:99,115,164,185`).
- `recycle_browser()` (`patchright_scraper.py:78-90`): shares `_start_lock`, no-ops if never launched or if `_active_scrapes > 0`, otherwise `close_browser()` then `start_browser()`. Registered as a 24h `AsyncIOScheduler` job in `main.py`'s `lifespan` (`main.py:57-61`), alongside `poll_prices`'s 6h job.
- `close_browser()` is called from exactly two places today: `recycle_browser()` and `lifespan`'s shutdown block (`main.py:78`).
- `poll_prices` (`jobs.py:22-45`) processes every active listing **sequentially** in one function call — plain `for item_id in item_ids: await process_item(...)`, no concurrency, the whole pass serialized by `_prices_lock`.
- `#41`'s ad-hoc first-scrapes (`_bounded_process_item`, `items.py`) are `spawn()`'d independently per listing on add, bounded by `_first_scrape_semaphore` (concurrency 3) — no single well-defined "batch end" the way `poll_prices` has, since separate HTTP requests can each spawn their own scrape at any time.
- `.doc/architecture.md`'s Polling Schedule table has a row documenting the recycle job (line 152).
- `tests/scraper/test_patchright.py` has three tests directly exercising `recycle_browser()` (never-launched no-op, skip-when-busy, closes-and-relaunches-when-idle) plus a fixture resetting `_active_scrapes` around each test.
- `tests/test_lifespan.py` asserts the recycle job is registered in `lifespan`'s scheduler setup.

### Target State
- New `PatchrightScraper.close_if_idle()` classmethod: closes only if the **global** `_active_scrapes` is back to 0. Both callers below go through this, not `close_browser()` directly — required because `poll_prices` and an ad-hoc add's batch run on the same event loop and can genuinely overlap; whichever one finishes last is the one that actually closes it.
- `poll_prices` calls `close_if_idle()` after its full sequential loop over `item_ids` completes — one check per poll cycle, not per listing, so non-adjacent Patchright-routed listings within the same cycle don't trigger a relaunch mid-cycle.
- `#41`'s ad-hoc path gains a new `_dispatch_first_scrapes()` helper in `items.py`: `create_item`/`create_listing` spawn *one* background task per request (not one per listing) that `gather()`s every listing in that request's own batch, then calls `close_if_idle()`. No debounce/timer — since `gather()` only returns once this specific request's entire known batch has finished, there's nothing more from *this* request that could still be coming; a genuinely new, unrelated request's next scrape is just an ordinary lazy relaunch.
- `recycle_browser()` classmethod removed entirely.
- The 24h scheduler job registration removed from `main.py`'s `lifespan`.
- `.doc/architecture.md`'s Polling Schedule row for the recycle job removed (or replaced with a row describing the new close-on-idle behavior, if that reads as worth documenting there).
- `_start_lock`'s double-checked-locking behavior for concurrent launches is **unchanged** — this issue only changes when the shared instance closes, not how it's shared while open.
- `_USER_DATA_DIR` (the on-disk persistent profile) is untouched by any of this — confirmed this session that `close_browser()` never references it, so closing more often has no effect on the bot-evasion value of the persistent profile.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/patchright_scraper.py`** — remove `recycle_browser()`.
- **`backend/app/scheduler/jobs.py`** — `poll_prices` gets an explicit `close_browser()` call after its loop; needs to import `PatchrightScraper`.
- **`backend/app/api/items.py`** — new `_dispatch_first_scrapes()` helper; `create_item` and `create_listing` each spawn one call to it instead of one `spawn()` per listing.
- **`backend/app/main.py`** — remove the daily recycle job registration from `lifespan`.
- **`.doc/architecture.md`** — remove (or replace) the recycle job's Polling Schedule row.
- **`backend/tests/scraper/test_patchright.py`** — remove the three `recycle_browser`-specific tests, add coverage for the new close-on-drain behavior instead.
- **`backend/tests/test_lifespan.py`** — remove the assertion that the recycle job is registered.

### Dependencies
- **`app/services/scraper/router.py`** — `RetailerRouter.get_price()` calls into `PatchrightScraper.get_price()` unchanged; not directly touched by this issue.
- **`#15`** (blocked by this issue, per `.doc/issues.md`) — Xvfb's own start/stop design assumes whatever browser-close model this issue lands on, not `#40`'s original persistent-until-recycle one.

### New Dependencies
None — no new packages, reuses `asyncio` primitives already in use.

### Breaking Changes
None externally — internal-only change to `PatchrightScraper`'s lifecycle and two scheduler-adjacent call sites. No API contract, request/response shape, or DB schema changes.
