# #15: Headless Chromium Bot Detection on Pi

## PR / Branch
Not applicable — this project doesn't use git branches (solo project, direct commits to `main`, deliberate — see `[[project_local_dev_workflow]]`).

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ✅ Done — 2 Major + 2 Minor found, all fixed | [review.md](review.md) |

## Success Criteria
<!-- Derived directly from .doc/issues.md's Issue #15 acceptance criteria -->
- [x] Smoke test `--patchright` passes on Pi Docker for: `deadstock.ca` (Shopify), `amazon.ca` — confirmed live: Shopify `ok $360.0`, Amazon `ok $594.27`
- [x] Dockerfile builds cleanly on Pi's ARM64 with `xvfb` installed — confirmed live, after fixing an unrelated dependency-pinning blocker found along the way
- [x] `start_browser()` starts the Xvfb subprocess before Chromium launch (with `DISPLAY` set), decoupled from `close_browser()`/`close_if_idle()` — only `stop_xvfb()`, called from `lifespan`'s real shutdown, ever kills it
- [x] BestBuy and SSENSE both re-tested against Xvfb specifically — confirmed live: BestBuy `ok $799.99` (was blocked headless), SSENSE `oos` (challenge cleared, real content parsed — this test product just isn't in stock)
- [x] Confirmed live: Xvfb's PID (`14`) survived a full Chromium close-and-relaunch cycle unchanged — a scrape after the cycle succeeded without Xvfb's process identity changing

## Estimated Effort
- Implementation: **1.25 hours**
- Testing (Pi hardware, user-executed): **0.75 hours**
- **Total: ~2 hours**
