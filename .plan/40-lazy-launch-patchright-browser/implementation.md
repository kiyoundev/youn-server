# #40: Implementation

## Steps

### 1. Lazy launch, guarded by a lock — ✅ done, verified live
- [x] Add `_start_lock: asyncio.Lock` to `PatchrightScraper` (class-body level — safe pre-3.10-deprecation-removal to construct outside a running loop; confirmed fine on this app's Python 3.10.12)
- [x] Rewrite `start_browser()` with double-checked locking (implemented as planned)
- [x] Call `start_browser()` at the top of `get_price()` — **scope note:** this needed both `PatchrightScraper.get_price()` **and** `AmazonCAScraper.get_price()` (a subclass override with its own duplicate early-return guard, not mentioned in the original plan text but same bug). Both now call `PatchrightScraper.start_browser()` explicitly (not `self`/`cls`) — calling a `@classmethod` through a subclass would bind `cls` to `AmazonCAScraper`, creating a second, separate `_context`/lock instead of sharing the base class's.
- [x] Verified live: `_context` starts `None`, lazily launches on first real `get_price()` call, real price returned (`AmazonCAScraper`, `$639.00`)
- [x] Verified live: 3 concurrent `get_price()` calls all needing Patchright simultaneously → exactly 1 browser launch (instrumented count), all 3 got correct results — confirms the actual concurrency-safety property this issue exists to deliver, not just the happy-path single-caller case

### 2. Browser lifecycle wiring — ✅ done
- [x] Confirmed no `start_browser()` call in `lifespan` startup (never existed — nothing to remove)
- [x] Added `close_browser()` to `main.py`'s `lifespan` shutdown block, alongside `finnhub.stop()` / `synology_client.close()`

### 3. Recycle mechanism — ✅ done
- [x] Added `PatchrightScraper._active_scrapes: int = 0` class attribute
- [x] Increment/decrement wired into **both** `get_price()` methods — the base class's and `AmazonCAScraper`'s override (same subclass duplication pattern as step 1's `start_browser()` fix). `AmazonCAScraper`'s counts once per call across its whole retry loop, not once per attempt.
- [x] `recycle_browser()` implemented exactly as planned, sharing `_start_lock` with `start_browser()`
- [x] Daily job registered in `main.py`'s `lifespan`, no `next_run_time` override (confirmed intentional — only `poll_prices` gets the immediate-first-run override)
- [x] Row added to `.doc/architecture.md`'s Polling Schedule table

### 4. Testing & Validation — ✅ all done, verified live (rebuilt local Docker image, Mac)
- [x] Single real `amazon.ca` scrape triggers browser launch, returns a real price (`$639.00`)
- [x] 3 concurrent `get_price()` calls all needing Patchright → exactly 1 browser launch (instrumented count), all 3 succeed (verified during step 1)
- [x] `recycle_browser()` while a scrape is genuinely in-flight (`asyncio.create_task` + a 50ms yield to let it get past `start_browser()`) → correctly detects `_active_scrapes == 1`, skips, context object unchanged; the in-flight scrape itself completes successfully, unaffected
- [x] `recycle_browser()` while idle → context object identity actually changes (confirms a real close+relaunch, not a silent no-op); a scrape immediately after still succeeds
- [x] `recycle_browser()` before any scrape has ever run → no-ops cleanly, `_context` stays `None`, no exception

### 5. Cleanup — ✅ done
- [x] `CHROMIUM_PATH`'s `os.environ.get(...)` read and the Dockerfile's `/etc/environment` write left as-is, per plan
- [x] Confirmed no leftover debug logging in the actual source diffs (`git diff` checked) — all test `print()` calls lived in one-off inline test commands, never touched the committed files
