# #40: Lazy-Launch Patchright's Browser, Guarded by a Lock

## PR / Branch
Not applicable — this project doesn't use git branches (solo project, direct commits to `main`, deliberate — see `[[project_local_dev_workflow]]`).

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done (recycle-mid-launch race resolved via shared lock) | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [x] `start_browser()` launches lazily from `get_price()`, guarded by `_start_lock` — not called unconditionally from `main.py`'s `lifespan`
- [x] `close_browser()` still called during `lifespan` shutdown
- [x] Concurrent callers that all need Patchright simultaneously result in exactly one browser launch, verified live
- [x] A real `amazon.ca` listing's scheduled scrape returns a real price, not `status: "error"`
- [x] `detect_scraper_type`'s Patchright fallback actually attempts a real headless-browser probe (unchanged code path, now backed by a working `start_browser()`)
- [x] First-use launch latency confirmed acceptable (a few seconds, well within this app's non-latency-sensitive scrape cadence)
- [x] `recycle_browser()` correctly no-ops when never launched, skips when a scrape is in-flight, closes+reopens when idle
- [x] Daily recycle job registered and firing on schedule, documented in `architecture.md`
- [x] A scrape immediately after a recycle succeeds normally

## Estimated Effort
- Implementation: **0.75 hours**
- Testing: **0.25 hours**
- **Total: ~1 hour**
