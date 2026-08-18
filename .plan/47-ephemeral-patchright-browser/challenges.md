# #47: Challenges & Notes

## Potential Challenges

1. **Thrashing within one `poll_prices` cycle if closed reactively instead of at the batch boundary.** `poll_prices` iterates listings sequentially and isn't guaranteed to have Patchright-routed listings adjacent to each other — a naive "close whenever `_active_scrapes` hits 0" applied uniformly would relaunch mid-cycle every time a non-Patchright listing runs between two Patchright ones. **Mitigated by:** giving `poll_prices` its own explicit end-of-loop close (implementation.md step 1), separate from the reactive debounce used for `#41`'s path. This is the main reason this issue doesn't use one single "close N seconds after idle" rule everywhere — the two callers have genuinely different shapes (one bounded synchronous batch vs. unbounded overlapping background tasks).

2. **Two adds landing back to back are no longer a special case — resolved by design, not by tuning.** Originally considered a debounce timer to absorb two `#41` adds arriving seconds apart; dropped once the design moved to grouping each request's listings into a single `gather()`. Since `_dispatch_first_scrapes()` only checks `_active_scrapes` after *its own* request's entire batch has fully drained, there's no "maybe one more from the same request is still coming" case a timer would have been guarding against — the batch is fully enumerated upfront. A second, *unrelated* request arriving moments later isn't a race to debounce against; it's just an ordinary lazy relaunch, no different from the very first launch ever.

3. **Residual race: a brand-new request's first scrape landing in the exact instant between another request's `gather()` returning and its `_active_scrapes == 0` check.** Microsecond-scale — asyncio event-loop scheduling, not a real wall-clock gap a human could produce (unlike the debounce-era concern about two adds seconds apart). Worst case: the browser closes right as it was about to be needed again, and the next `start_browser()` call just relaunches it — the normal lazy-launch path, at a small one-time latency cost, not a correctness bug. Same class of accepted gap as `#40`'s own "browser crash outside the recycle cycle" note (challenges.md, `#40`) — not worth engineering around at this app's scale.

4. **`poll_prices` and an ad-hoc add's batch can genuinely overlap — both run on the same event loop.** Surfaced directly by this question during planning: if `poll_prices`'s loop finished and called `close_browser()` *unconditionally* (the first draft of this plan), it would tear the context down out from under an ad-hoc batch still mid-flight at that exact moment — the ad-hoc scrape's page gets yanked, comes back `status="error"` (via `get_price()`'s existing broad exception guard, so not a crash, but a real avoidable failure). **Resolved by design, not by luck:** both callers now go through the same `close_if_idle()` helper, which checks the *global* `_active_scrapes` — not "is my own batch done," but "is anyone, from either path, still using it." Whichever caller finishes last is the one that actually closes it; the other's earlier arrival at "I'm done" correctly sees non-zero and skips closing. Same residual microsecond-scale race as challenge 3 applies here too (a new batch starting in the exact instant between the check and the close) — not a new class of risk, same accepted gap.

5. **Regression risk to `#40`'s core guarantee.** This issue only intends to change *when* the browser closes, not the concurrent-launch-sharing mechanism (`_start_lock`, double-checked locking) that makes concurrent callers share one instance. Real risk is accidentally weakening that while restructuring `close_browser()`'s call sites — the existing 3-concurrent-callers-one-launch test (from `#40`) should be re-run, not just trusted to still pass by inspection.

6. **`#15` is blocked on this issue's shape, not just its existence.** `#15`'s Xvfb design (discussed this session, not yet written into its own plan) assumes Xvfb persists across whatever the browser's close/reopen cycle becomes here — i.e., Xvfb should NOT be torn down by either `poll_prices`'s explicit close or `#41`'s debounced close, only by real app shutdown. This issue's `close_browser()` must stay scoped to `_context`/`_playwright` only, never touching an Xvfb subprocess (which doesn't exist yet, but the boundary matters for `#15` to build on cleanly afterward).

## Key Differences

| Aspect | `#40` (current, shipped) | `#47` (this issue) |
|--------|---------------------------|----------------------|
| Browser lifetime once launched | Indefinite, until daily recycle or shutdown | Until the current batch/idle-window drains |
| Idle RAM cost | ~100–250MB continuously between uses | ~0 between batches/bursts |
| Recycle job | Daily `AsyncIOScheduler` job, dedicated `recycle_browser()` method | Removed — nothing lives long enough to need it |
| `poll_prices` behavior | Browser stays open across the whole 6h gap until next cycle | Browser closes at the end of each cycle's loop |
| `#41` ad-hoc adds | Share the persistent instance, no close between adds | One `spawn()` per *request* (grouped `gather()` over that request's listings, was one per listing); closes once its own batch drains and the global `_active_scrapes` confirms nothing else is using it |
| Concurrent-launch sharing (`_start_lock`) | Unchanged | Unchanged — not in scope to modify |
| Bot-evasion (persistent profile) | Cookies/history survive on disk regardless | Same — confirmed `close_browser()` never touches `_USER_DATA_DIR` |

## Rollback Plan

1. Revert `backend/app/services/scraper/patchright_scraper.py`, `backend/app/scheduler/jobs.py`, `backend/app/api/items.py`, and `backend/app/main.py` to their pre-change state (`git checkout` or manual revert — no branch exists to simply not-merge, per this project's direct-to-`main` workflow).
2. Revert `.doc/architecture.md`'s Polling Schedule row change.
3. Restore the three removed `recycle_browser` tests in `tests/scraper/test_patchright.py` and the lifespan job-registration assertion in `tests/test_lifespan.py`.
4. Rebuild and redeploy (`docker compose up -d --build backend`, locally and on the Pi).
5. Verify: `poll_prices` still runs its 6h cycle correctly, `#41`'s ad-hoc adds still scrape successfully, non-Patchright scrapers (HTTPScraper-only sites) are unaffected either way since this change is scoped entirely to `PatchrightScraper`'s lifecycle.

No data/schema involved — trivially revertible, no migration or backfill concerns. Note: reverting after `#15` has landed on top of this issue's shape would need `#15`'s Xvfb wiring reverted or re-checked too, since its design assumes this issue's close-on-idle model, not `#40`'s original persistent one.
