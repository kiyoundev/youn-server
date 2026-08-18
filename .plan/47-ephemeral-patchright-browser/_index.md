# #47: Ephemeral Patchright Browser (Close on Idle, Drop the Daily Recycle)

## PR / Branch
Not applicable — this project doesn't use git branches (solo project, direct commits to `main`, deliberate — see `[[project_local_dev_workflow]]`).

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ✅ Done | [review.md](review.md) |

## Success Criteria
- [x] `poll_prices` closes the Patchright browser after its full sequential pass over active listings completes, not reactively per-listing — verified with a mixed batch (Patchright-routed listings non-adjacent in iteration order) that it doesn't thrash open/close mid-cycle. Unit-tested (`test_poll_prices_closes_browser_once_after_full_cycle`) and confirmed live via the on-startup `poll_prices` run (see `review.md` for the log timeline)
- [x] `#41`'s ad-hoc add-time scrapes correctly share one browser instance across concurrent adds within one request (unchanged `_start_lock` behavior); each request's batch, once fully drained (`gather()` over its own listings), closes the browser only if the global `_active_scrapes` confirms no other request is still using it
- [x] `recycle_browser()`, its daily scheduler job in `main.py`'s `lifespan`, and its Polling Schedule row in `.doc/architecture.md` are removed
- [x] Confirmed live: the browser's `_context` identity actually changes across a close-then-reopen cycle (proves real teardown/relaunch, not a silent no-op) — two separate ad-hoc adds produced two distinct context ids (`281472476283904` then `281472482995568`)
- [x] Confirmed live: a scrape that arrives after the browser has closed relaunches correctly and returns a real price, same as any other lazy-launch trigger — the second add above returned a real price (`$209.0016`, `status: "ok"`) off the freshly relaunched context
- [x] No regression to `#40`'s existing guarantees: concurrent callers still result in exactly one browser launch, not one per caller — `test_start_browser_concurrent_callers_launch_once` untouched and passing; also confirmed live during the manual poll_prices vs. ad-hoc-add overlap test (one shared context, not two)

## Estimated Effort
- Implementation: **1.5 hours**
- Testing: **0.5 hours**
- **Total: ~2 hours**
