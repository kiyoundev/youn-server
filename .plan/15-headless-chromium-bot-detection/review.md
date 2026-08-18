# #15: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

### Summary
Adds a lazily-launched, lifecycle-decoupled Xvfb virtual display so Patchright's Chromium can run genuinely headed (bypassing BestBuy/SSENSE's headless-detection) on Pi OS Lite's display-less environment, plus an incidentally-discovered dependency-pinning fix for `patchright`/the Docker base image. Solid design — the Xvfb/Chromium lifecycle decoupling is correctly built and well-tested (19 new/updated tests, live-verified on Pi). Two real gaps worth addressing before considering this fully closed.

**Verdict**: Request Changes → **All findings fixed**, see status notes below.

### Major Issues (Should Fix)

#### 1. `patchright_scraper.py:60-77` — Correctness: PID-liveness check doesn't verify process *identity*, only existence — ✅ **Fixed**
New module-level `_read_proc_comm(pid)` reads `/proc/{pid}/comm` and confirms it's actually `"Xvfb"` before trusting a PID that passed the `os.kill(pid, 0)` existence check; a mismatch is now treated the same as a stale lock (cleaned up, reported not-running). Isolated into its own patchable function since this dev machine (Mac) has no `/proc` to read from for real. New tests: `test_xvfb_already_running_true_for_live_pid_with_matching_comm`, `test_xvfb_already_running_false_when_pid_reassigned_to_different_process` (Minor #2, below).
- **Current**:
  ```python
  os.kill(pid, 0)  # signal 0: existence check only, doesn't kill
  ```
  followed by `return True` (treated as "Xvfb is genuinely running").
- **Failure scenario**: Xvfb dies abnormally (e.g. OOM-killed, not a clean `.terminate()` — which *does* clean up its own lock, so this only matters for a hard kill) without removing its lock file. Given this app runs continuously for days/weeks, if the OS's PID counter later reassigns that exact PID to an unrelated process (real on constrained ARM environments with a smaller `pid_max`, and Pi is exactly that), `_xvfb_already_running()` reports `True` for a process that isn't Xvfb at all. `start_browser()` then skips spawning, sets `DISPLAY=:99` anyway, and Chromium's connection to a display nothing is actually serving fails — a silent, hard-to-diagnose production break (scrapes degrading to `error` with no obvious cause in the logs pointing at Xvfb).
- **Suggested**: cross-check the PID's actual command name before trusting it, not just that some process with that number exists:
  ```python
  try:
      with open(f"/proc/{pid}/comm") as f:
          if f.read().strip() != "Xvfb":
              raise ProcessLookupError  # PID recycled to something else
  except FileNotFoundError:
      raise ProcessLookupError
  ```
  (Same branch already handles cleanup — this just tightens what counts as "genuinely alive.") `/proc` is always available in this Linux container.
- **Context**: acknowledged this is Xvfb's own lock-file design being fragile by nature (PID files are a known-legacy pattern) — but the fix is cheap and fully within this code's own control, so worth closing rather than inheriting the limitation as-is.

#### 2. `patchright_scraper.py:60-71,148-152` — Design: synchronous I/O/subprocess calls inside an async app, deviating from established convention — ✅ **Fixed (subprocess handling), explicitly documented (file I/O)**
Spawning: `subprocess.Popen` → `await asyncio.create_subprocess_exec(...)`, matching `trading_agents.py`/`analysis.py`'s existing pattern. Liveness check: `.poll()` → `.returncode` (the `asyncio.subprocess.Process` equivalent, no blocking call needed). Shutdown: `stop_xvfb()`'s `.wait()` is now properly `await`ed. `_xvfb_already_running()`'s tiny file/PID reads were deliberately **not** wrapped in `run_in_executor()` — per the review's own framing, this is now a stated decision (added to the method's docstring) rather than a silent deviation: the reads are a few bytes each, and thread-pool dispatch would cost more than the blocking call itself.
- **Current**: `_xvfb_already_running()`'s file `open()`/`os.kill()`/`os.remove()`, plus `stop_xvfb()`'s `Popen.wait()`, are all blocking calls inside `async def` methods.
- **Why it matters here specifically**: `_xvfb_already_running()` runs *while `_start_lock` is held* — the same lock `#40` built specifically to serialize concurrent Patchright callers (e.g. a 3-URL bulk add). Blocking the single-threaded event loop while holding that lock doesn't just delay other Patchright callers, it briefly stalls *every* coroutine in the app, not a narrow concern.
- **Precedent this deviates from**: this codebase already has an established async-subprocess pattern — `trading_agents.py`/`analysis.py` both use `asyncio.create_subprocess_exec(...)` with `asyncio.subprocess.PIPE`, not the blocking `subprocess` module. The new Xvfb code is the one place introducing the blocking variant.
- **Impact in practice is small** — the file read is a few bytes, `os.kill(pid, 0)` is fast, and `stop_xvfb()` only ever runs once at real shutdown (not a hot path) — so this isn't causing an observed problem, just a real inconsistency with how the rest of the app handles subprocess/blocking-I/O concerns.
- **Suggested**: swap `subprocess.Popen` for `asyncio.create_subprocess_exec`, and wrap `_xvfb_already_running()`'s file I/O in `asyncio.get_running_loop().run_in_executor(None, ...)` if keeping it synchronous is a concern — or, given the actual blocking window is genuinely tiny (microseconds) and this only runs at browser-launch/shutdown boundaries (not per-scrape), it's reasonable to explicitly accept this as a deliberate trade-off — but that should be a stated decision, not an unstated deviation from the pattern used two files over.

### Minor Issues (Nice to Have)

#### 1. `patchright_scraper.py:63` — Robustness: unvalidated PID from lock file — ✅ **Fixed**
Added `if pid <= 0: return False` before the `os.kill()` check. New test: `test_xvfb_already_running_false_for_non_positive_pid`.

#### 2. `test_patchright.py` — no test for Major #1's PID-reuse scenario — ✅ **Fixed**
Added alongside Major #1's fix, patching the new `_read_proc_comm()` directly (works around this dev machine having no real `/proc`): `test_xvfb_already_running_false_when_pid_reassigned_to_different_process` — a live PID whose `_read_proc_comm()` returns something other than `"Xvfb"` is correctly treated as not-running, with the stale lock cleaned up.

### Praise
- **The core design property — Xvfb fully decoupled from Chromium's `close_if_idle()` cycle — is correctly built and thoroughly protected.** `test_close_browser_does_not_touch_xvfb_process`/`test_close_if_idle_does_not_touch_xvfb_process` are exactly the tests that matter for this issue's actual point, not just incidental coverage.
- **Genuinely excellent incident response mid-implementation**: the smoke-test collision (`Fatal server error: Server is already active`) was root-caused correctly (process-local `_xvfb_process` memory not surviving across separate script invocations) rather than papered over, and the fix (`_xvfb_already_running()`) is a real improvement, not a band-aid.
- **The dependency-pinning fix is a genuinely valuable find**, not scope creep for its own sake — it was a real, silently-recurring bug (bit twice in one session) that would have kept breaking future incidental rebuilds regardless of this issue. The comment explaining *why* (`mcr.microsoft.com` publishes per-minor tags, PyPI publishes per-patch releases, no exact match possible) is exactly the kind of non-obvious reasoning worth preserving in-line.
- **Comment quality throughout is excellent** — `_xvfb_process`'s class-level docstring, `_xvfb_already_running()`'s docstring, and `stop_xvfb()`'s docstring all explain *why*, not just *what*, and correctly cross-reference the design decisions they depend on (`#47`'s cycling frequency, `_start_lock`'s reuse).
- **Test structure is thoughtful** — the `stub_xvfb_already_running` fixture being opt-in (not autouse) specifically so the lock-file tests can exercise the real implementation is the right call, not the more common mistake of over-stubbing everything uniformly.

### Questions for Author
- Given Major #2's finding: is the blocking I/O a considered trade-off (acceptable given the narrow, infrequent call sites) or worth fixing regardless of practical impact, for consistency with the rest of the codebase's subprocess handling?

### Test Coverage Assessment
- [x] Happy path tested (spawn when absent, skip when alive, respawn when dead, reuse when externally alive)
- [x] Error/edge cases tested (stale lock cleanup, no lock file, malformed/non-positive PID, `stop_xvfb()` no-op)
- [x] Core design-property regression tests present (`close_browser()`/`close_if_idle()` non-interference)
- [x] PID-reuse/identity-spoofing edge case (Major #1) — now covered (`test_xvfb_already_running_false_when_pid_reassigned_to_different_process`)

### Checklist
- [x] No SQL injection / auth issues (no DB or auth surface touched)
- [x] No shell-injection risk (subprocess spawn uses argument list, not `shell=True`; all args are hardcoded constants)
- [x] Performance — subprocess handling now matches codebase's async convention; remaining tiny synchronous file reads are a stated, documented trade-off, not an oversight
- [x] Code is readable, exceptionally well-commented
- [x] Tests are adequate and well-targeted (21 tests, 315/315 full suite passing)
- [x] Live-verified on real target hardware (Pi ARM64), not just unit-tested

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
