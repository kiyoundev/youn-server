# #40: Review

## AI Review

Run via `/code-reviewer:review` against all staged changes (2026-08-15) — scope covered the full staged diff (`#40`'s core work plus the Dockerfile version bump and scraper `config.py` constant extraction that landed in the same staging pass).

**Intent:** Make `PatchrightScraper`'s shared browser launch lazily on first real use (guarded by a lock against duplicate-launch races), add a daily recycle mechanism for long-uptime resilience, bump the Playwright base image to fix a version-mismatch crash, and extract previously-inlined scraper timeout/retry magic numbers into named constants.

### Critical
None.

### Major — all fixed, see outcomes below

1. **`test_patchright_no_context_returns_error` no longer tests what it claims — and now makes a real network call during a unit test.**
   `tests/scraper/test_patchright.py:22-24` asserts `get_price()` returns `status="error"` when `_context is None`, written against the *old* short-circuit behavior (`if _context is None: return error`). That branch is gone — `get_price()` now calls `await PatchrightScraper.start_browser()` instead. Verified live: `start_browser()` actually succeeds in ~0.7s in this environment, so the test now launches a real Chromium instance and makes a real request to `https://example.com/product`. It still passes only because that real page has no extractable price — right assertion, entirely wrong reason. Worse than a broken test: a green checkmark that no longer verifies the thing its name claims, and slow/flaky/environment-dependent wherever it runs next (fails hard in CI without Playwright browsers or network access).

   Fix: mock `PatchrightScraper.start_browser`/`_context` rather than relying on the real thing, and assert what actually matters now — e.g., that `get_price()` calls `start_browser()` before touching `_context`.

2. **No test coverage for any of this PR's actual new behavior.** The lock-guarded dedup (concurrent callers → exactly one launch), `recycle_browser()`'s three branches (never-launched no-op, in-flight skip, idle close+reopen), and the `_active_scrapes` counter's increment/decrement balance were all verified this session — but only via ad hoc `python3 -c` scripts, never captured as permanent pytest coverage. Exactly the kind of concurrency-correctness code where a future refactor could silently reintroduce the duplicate-launch race or a recycle-mid-scrape bug with nothing to catch it.

3. **Pre-existing leak, now more exercised: a failed `launch_persistent_context()` orphans the Playwright driver process.** In `start_browser()`:
   ```python
   cls._playwright = await async_playwright().start()
   cls._context = await cls._playwright.chromium.launch_persistent_context(...)  # if this throws...
   ```
   If the second line throws, `cls._playwright` is left set (a live driver subprocess) while `cls._context` stays `None`. The exception propagates, gets caught by `get_price()`'s outer `except`, returns `status="error"` — silently. Next call to `start_browser()` sees `_context is None`, re-enters, and does `cls._playwright = await async_playwright().start()` again — overwriting the reference to the previous still-running driver process without stopping it. Every failed launch leaks one orphaned Playwright driver.

   Predates this PR (same shape in the original code) — but this PR meaningfully increases the blast radius: previously `start_browser()` was never called at all in production (the whole reason `#40` exists), so this path was never exercised. Now it's called defensively on every single `get_price()`, meaning a transient failure leaks a process *every scrape attempt* until cleared, not once ever. Suggested fix:
   ```python
   async with cls._start_lock:
       if cls._context is not None:
           return
       try:
           executable_path = os.environ.get("CHROMIUM_PATH")
           cls._playwright = await async_playwright().start()
           cls._context = await cls._playwright.chromium.launch_persistent_context(...)
           cls._browser = None
       except Exception:
           if cls._playwright:
               await cls._playwright.stop()
           cls._playwright = None
           raise
   ```

### Minor — both fixed

4. **Fixed.** `reset_patchright_state` fixture now saves/restores `_start_lock` too (a fresh `asyncio.Lock()` per test), alongside the `_active_scrapes` reset already added when the file was rewritten for the Major fixes. Documented in the fixture's own docstring as cheap insurance rather than a confirmed bug — Python 3.10+ locks don't actually bind to a specific event loop, so the cross-test risk was real but low; fixed anyway for full, consistent isolation of every piece of class state, not just some of it.

5. **Fixed.** `AMAZON_MAX_RETRIES`'s docstring in `config.py` no longer poses this as an open question — resolved into an explicit decision: the asymmetry stays, because the scheduled `poll_prices` cycle itself already acts as every scraper's real retry (a failed attempt just waits up to 6h for the next one, same effective outcome as an immediate in-process retry). Amazon's own extra retries exist for a narrower reason — DOM-readiness flakiness right after a fresh navigation, not "did the request succeed at all." Documented as revisit-if-another-retailer-shows-the-same-flakiness, not left as a dangling question.

### Praise

- Double-checked locking implementation is correct — traced independently, not just trusted by pattern-matching: fast-path check outside the lock, re-check inside, `_active_scrapes`'s increment placed with zero `await` between it and `start_browser()`'s return (no yield point for a recycle to sneak in before the counter's actually incremented). Matches the live 3-way-concurrent test's result (exactly 1 launch).
- Explicit `PatchrightScraper.start_browser()` calls (never `self`/`cls`) in the `AmazonCAScraper` override correctly avoid the classmethod-through-subclass footgun — calling it via `self`/`cls` would've bound to `AmazonCAScraper`, silently creating a second browser instead of sharing the base class's. Called out explicitly in comments, not left implicit.
- `recycle_browser()` reusing `_start_lock` instead of a second lock correctly closes the recycle-vs-launch race with zero new primitives, and is commented as a deliberate reuse, not an accident.
- Dockerfile version bump was diligence-checked, not just tried: confirmed the exact Chromium build (`1228`) that patchright `1.61.2` needed actually exists in the target image, confirmed Python version compatibility, confirmed a full `chrome` binary (not just `headless_shell`) is present — before committing to the change.
- Constants extraction is honest about its own limits — the `config.py` comment explicitly states these are unmeasured `#3`-era defaults, not evidence-backed tuning, rather than implying more rigor went into the original numbers than actually did.

### Questions

- Should `recycle_browser()`'s `close_browser()` call (inside the lock) be wrapped in its own try/except? If `_context.close()` throws, the exception propagates uncaught out of the scheduled job — does APScheduler swallow/log that gracefully, or would a persistently-throwing `close()` mean recycling silently never succeeds again? Not verified either way this session.

### Verdict

**Approved — all three Major findings fixed and verified.**

- **#1 fixed:** `tests/scraper/test_patchright.py` rewritten to mock `start_browser()`/`_context` at the boundary, matching the established mocking pattern in `test_router.py` — no real network/browser calls in any scraper test anymore.
- **#2 fixed:** Added new tests for the actual new behavior — concurrent-callers-launch-once (via a slow fake `launch_persistent_context()` widening the race window, asserting `launch_count == 1`), and all three `recycle_browser()` branches (never-launched no-op, in-flight skip, idle close+reopen).
- **#3 fixed:** `start_browser()`'s launch steps wrapped in try/except — on failure, stops the orphaned `_playwright` driver (if one was started) and resets state to clean `None`s before re-raising, exactly as proposed above. Covered by a dedicated test (`test_start_browser_cleans_up_playwright_on_launch_failure`) that asserts `.stop()` was actually called and state was reset.
- **Bonus catch while re-running the full suite:** `tests/test_lifespan.py`'s existing test broke for a real reason — it checked `scheduler.add_job.call_args` (always the *most recent* call), and this PR added a second `add_job` call (the daily recycle job) after the existing `poll_prices` one, so the test was silently checking the wrong call's kwargs. Fixed by asserting on `call_args_list` explicitly for both calls, and added an assertion that `PatchrightScraper.close_browser()` is awaited on shutdown.
- **Full suite: 278 passed, 0 failed**, in 1.63s. Also re-verified live against the rebuilt Docker image — a real `AmazonCAScraper` scrape still returns the correct price after the leak-fix change, confirming no functional regression.

---

## Tech Lead Review
<!-- Populated when review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
