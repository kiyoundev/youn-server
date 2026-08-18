# #47: Implementation

## Steps

### 1. `PatchrightScraper.close_if_idle()` — shared close-decision, used by both callers
- [ ] Add `PatchrightScraper.close_if_idle()` classmethod: `if cls._active_scrapes == 0: await cls.close_browser()`. This is the one place either caller checks the *global* counter before tearing anything down — critical because `poll_prices` and an ad-hoc add's batch run on the same event loop and can genuinely overlap; if `poll_prices`'s own loop finishes while an ad-hoc batch is still mid-flight, an unconditional `close_browser()` would close the context out from under the ad-hoc batch's still-open pages (they'd error out via `get_price()`'s existing broad `except Exception`, not crash, but a real avoidable failure)
- [ ] After `jobs.py`'s `for item_id in item_ids: await process_item(...)` loop finishes (inside the existing `_prices_lock` block, before it releases), call `await PatchrightScraper.close_if_idle()` — not `close_browser()` directly
- [ ] Import `PatchrightScraper` into `jobs.py` (not currently imported there — only `RetailerRouter` is)

### 2. `#41`'s ad-hoc path — grouped `gather()` per add-request, close on real batch drain
- [ ] Add `_dispatch_first_scrapes(listing_ids: list[int], semaphore: asyncio.Semaphore, queue: asyncio.Queue) -> None` in `items.py`: `await asyncio.gather(*(_bounded_process_item(lid, semaphore, queue) for lid in listing_ids))`, then `await PatchrightScraper.close_if_idle()` (step 1's shared helper). (`_bounded_process_item` already never raises — per its own docstring — so no `return_exceptions=True` needed on the `gather()`.)
- [ ] `create_item`: replace the per-listing `for listing in product.listings: spawn(_bounded_process_item(...))` loop with a single `spawn(_dispatch_first_scrapes([listing.id for listing in product.listings], ...))` — one background task per *request*, not one per listing
- [ ] `create_listing`: same helper, single-element list — unifies both call sites on one mechanism instead of `create_item` and `create_listing` diverging
- [ ] `close_if_idle()` checking the **global** `_active_scrapes` (not a per-request local count) is what makes this safe against overlapping requests *and* against overlapping with `poll_prices`: if a second, unrelated add-request's batch — or a scheduled poll cycle — is still running concurrently, its own scrapes have already incremented the shared counter, so the check correctly sees non-zero and skips closing. No coordination needed between the two callers beyond both going through the same shared helper.
- [ ] No debounce/timer needed — since `gather()` only returns once every listing in *this specific request's* known batch has fully finished, there's no "maybe one more from the same request is still coming" case left to guard against with a timer. A genuinely new, unrelated request's first scrape landing right after a close is just an ordinary lazy relaunch, same as the very first use ever

### 3. Remove `recycle_browser()` and its scheduler job
- [ ] Delete `PatchrightScraper.recycle_browser()` classmethod (`patchright_scraper.py:78-90`)
- [ ] Remove the `scheduler.add_job(PatchrightScraper.recycle_browser, "interval", hours=24)` registration from `main.py`'s `lifespan` (`main.py:57-61`)
- [ ] Confirm `_active_scrapes`'s in-flight check (previously `recycle_browser`'s `> 0` skip) is still exercised somewhere relevant after removal — it's now load-bearing for step 2's debounce logic instead

### 4. Docs
- [ ] Remove (or replace with a close-on-idle description) the "Patchright browser recycle" row in `.doc/architecture.md`'s Polling Schedule table (line 152)
- [ ] Update any comment in `patchright_scraper.py` that references `recycle_browser()` by name (e.g. the `_active_scrapes` docstring comment at line 32)

### 5. Testing & Validation
- [ ] Remove `test_recycle_browser_noop_when_never_launched`, `test_recycle_browser_skips_when_scrape_in_flight`, `test_recycle_browser_closes_and_relaunches_when_idle` from `tests/scraper/test_patchright.py`
- [ ] Remove the recycle-job-registered assertion from `tests/test_lifespan.py`
- [ ] Add: `poll_prices` closes the browser after a mixed-batch cycle (Patchright-routed listings non-adjacent in iteration order) — verify no relaunch happens mid-cycle (e.g. instrument/count launches across the batch)
- [ ] Add: `_dispatch_first_scrapes` closes the browser once all listings in its `gather()` have finished and `_active_scrapes` is back to 0 — verify context identity actually changes on the next use (proves a real teardown, not a no-op)
- [ ] Add: `_dispatch_first_scrapes` does **not** close when a second, unrelated batch is still concurrently in flight (its scrapes keep the global `_active_scrapes` above 0) — verify the shared context survives, unaffected by the first batch's own drain-and-check
- [ ] Live: a scrape that arrives after the browser has actually closed relaunches correctly and returns a real price
- [ ] Live: concurrent callers within one batch (e.g. a 3-URL add) still share exactly one launch (re-verify `#40`'s original guarantee still holds — this issue must not regress it)

### 6. Cleanup
- [ ] Grep for any other reference to `recycle_browser` left behind (docs, comments, `.doc/issues.md`'s own `#40` write-up notes it if relevant — leave `#40`'s historical write-up as an accurate record of what shipped at the time, don't rewrite history there)
- [ ] Remove debug logging/instrumentation added for live verification before considering this done
