# #41: Challenges & Notes

## Potential Challenges

1. **FastAPI's `BackgroundTasks.add_task()` runs tasks sequentially, not concurrently — the obvious first-instinct API for this would silently defeat the whole concurrency design.** Surfaced during planning, before any code was written: `BackgroundTasks` queues and awaits each added task one after another after the response is sent, not via `asyncio.gather` or similar. Adding N listings' scrapes as N separate `background_tasks.add_task(...)` calls would run them one at a time — the `Semaphore(3)` bound would then be meaningless (nothing's ever concurrent enough to need bounding). Resolved by not using `BackgroundTasks` for this at all — using `spawn()` (real `asyncio.create_task` + a registry preventing premature garbage collection) instead, the same pattern `trading_agents.py` already uses for its own independent background work.

2. **Concurrent heavy-scrape behavior against Patchright's shared browser context is new territory, not yet verified even after `#40`.** `#40` verified concurrent *launches* (N callers racing to start the browser, exactly one launch wins) — this issue is the first time multiple scrapes run *against an already-running* shared context simultaneously, each opening its own tab. Patchright's context design should support this (that's the whole point of a persistent context — multiple pages), and `#10.2`'s lighter routing-probe concurrency is suggestive precedent, but neither is the same as N real page-loads-with-full-rendering happening at once. Must be verified live per `implementation.md`'s testing step — genuinely, not assumed.

3. **Two separate concurrency bounds, deliberately not shared.** `items.py` already has `_PROBE_CONCURRENCY = 3` bounding `detect_scraper_type`'s lightweight routing probes (`#10.2`). This issue adds a *second*, numerically-identical-but-separate `Semaphore(3)` for the heavier first-scrape dispatch. Sharing one semaphore between both would mean a burst of routing probes and a burst of first-scrapes (which can happen concurrently — different requests, unrelated in time) compete for the same 3 slots, potentially starving one operation behind the other despite them having very different costs (a probe is typically much faster than a full scrape). Kept separate on purpose — the matching number (3) is coincidental, not a reason to conflate them.

4. **Spawned tasks must outlive the HTTP request/response cycle — already proven safe, not a new risk.** The response returns while scrapes are still running in the background. Since `spawn()`'s `asyncio.create_task()` schedules on the app's single shared event loop (not tied to any individual request's connection), the task keeps running regardless of that specific HTTP connection closing — exactly how `trading_agents.py`'s existing `spawn()` usage already works today (fires after an alert, independent of any request). Not a new risk this issue introduces, just confirming the existing pattern's guarantee actually covers this new call site too.

5. **Concurrent extra DB sessions.** Each `process_item` call opens its own `AsyncSessionLocal()` — up to 3 extra concurrent sessions from this path alone (bounded by the semaphore), on top of whatever else the app is doing (API requests, a `poll_prices` cycle if one happens to overlap). Not independently verified against SQLAlchemy's configured pool size in this plan — low risk at this app's single-user scale, but worth a note rather than silent assumption.

## Key Differences

| Aspect | `#10.2`'s bulk-add probing | This issue's first-scrape |
|--------|---------------------------|----------------------------|
| Operation | `detect_scraper_type` — lightweight, HTTP-first with Patchright fallback only on error | Full `_process_item`-style scrape — real page render, up to ~30s |
| Timing | Synchronous, inside the request (response waits for it) | Asynchronous, after the response returns |
| Dispatch mechanism | `asyncio.gather` directly inside the request handler | `spawn()` — independent tasks outliving the request |
| Concurrency bound | `_PROBE_CONCURRENCY` (3) | A separate `Semaphore(3)`, not shared with the above |
| Verified safe under concurrency | Yes (`#10.2`) | Not yet — this issue's own testing step covers it |

## Rollback Plan

1. Revert `backend/app/api/items.py`'s dispatch wiring, `backend/app/scheduler/jobs.py`'s rename/re-export, `backend/app/services/product_status.py`'s `"processing"` branch, and `backend/app/core/background_tasks.py` (delete, restore `spawn()` back into `trading_agents.py`).
2. Revert `frontend/src/lib/api/items.ts` and `frontend/src/app/watchlist/page.tsx`'s UI changes.
3. Rebuild and redeploy both Mac local dev and the Pi.
4. Verify: existing scheduled `poll_prices` scraping and manual `POST /api/poll/prices` still work unaffected — this issue only adds a new trigger path, doesn't change the existing one's logic.

No DB migration involved — `"processing"` is a computed status value, not a stored column, so nothing to backfill or roll back at the data layer.
