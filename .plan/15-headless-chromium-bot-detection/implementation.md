# #15: Implementation

## Steps

### 1. Dockerfile — install Xvfb
- [x] Merge `xvfb` into the existing `python3-venv` apt-get install line in `backend/Dockerfile` (avoids an extra image layer, per the issue's own note):
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends python3-venv xvfb \
      && rm -rf /var/lib/apt/lists/*
  ```

### 2. `PatchrightScraper` — Xvfb subprocess, decoupled lifecycle
- [x] Add `_xvfb_process: subprocess.Popen | None = None` as a new classvar, alongside `_context`/`_playwright`/`_start_lock`/`_active_scrapes`
- [x] Import `subprocess` at the top of `patchright_scraper.py` (`signal` not needed — `Popen.terminate()` sends `SIGTERM` on its own)
- [x] Inside `start_browser()`'s existing `_start_lock` block, **before** the `launch_persistent_context()` call: if `_xvfb_process is None or _xvfb_process.poll() is not None` (not running or has died), spawn `subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])` and set `os.environ["DISPLAY"] = ":99"`. No readiness-pause added yet — deferred to live Pi testing (step 4) to confirm whether it's actually needed before adding one preemptively.
- [x] Flip `launch_persistent_context(...)`'s `headless=True` to `headless=False`
- [x] Add `PatchrightScraper.stop_xvfb()` classmethod: if `_xvfb_process` is set, terminate it (`.terminate()`, then `.wait()`), clear the reference. No lock — only ever called once, from `lifespan`'s real shutdown.
- [x] Confirmed `close_browser()` and `close_if_idle()` are untouched — neither references `_xvfb_process`
- [x] **Added beyond the original plan, discovered during Pi testing:** `_xvfb_process` is process-local memory — it doesn't survive across separate `python` process invocations (e.g. `smoke_test.py` run more than once via `docker compose exec` against the same long-lived container). Repeated smoke-test runs each spawned their own orphaned Xvfb, colliding on `:99`'s lock file (`Fatal server error: Server is already active for display 99`). Added `_xvfb_already_running()` (staticmethod): reads the holder PID from `/tmp/.X99-lock`, checks liveness via `os.kill(pid, 0)`, cleans up a stale lock (dead PID) so a fresh Xvfb can bind, and reports a genuinely live one as still running (reused, not respawned) either way. Wired into `start_browser()`'s spawn condition alongside the existing `_xvfb_process.poll()` check. Not a production concern (one continuous process there), but a real robustness gap worth closing regardless.

### 3. `main.py` — wire `stop_xvfb()` into real shutdown only
- [x] Add `await PatchrightScraper.stop_xvfb()` to `lifespan`'s shutdown block, immediately after the existing `await PatchrightScraper.close_browser()` call
- [x] Confirmed exactly one caller of `stop_xvfb()` in the whole codebase

### 4. Pi-side validation — user-executed (per this project's established ops-issue pattern, `#13`/`#40`)
- [x] **Step A (pre-Xvfb baseline)** — attempted, surfaced a real prerequisite blocker instead of a clean baseline: the Pi's running container was still on the stale `v1.44.0-jammy` image despite the repo's Dockerfile having been bumped to `v1.61.0-jammy` in an earlier commit — `git pull`ing a commit never rebuilds a running container on its own. Also needed `docker compose up -d --build` (recreates the container), not bare `build` (only builds the image, leaves the old container running unchanged).
- [x] **Discovered mid-Step-A, fixed inline (outside original scope):** a real, recurring dependency-pinning bug — `requirements.txt`'s `patchright>=1.44,<2.0` open range let pip resolve a newer client than the Dockerfile's pinned image build, twice in a row (`1.61.2` vs `v1.44.0-jammy`, then `1.62.1` vs `v1.61.0-jammy`). Root cause: `mcr.microsoft.com` only publishes per-**minor**-version jammy tags (`v1.61.0-jammy`, `v1.62.0-jammy`), while PyPI only has patchright's per-**patch** releases (`1.61.1`, `1.61.2`, `1.62.1`) — no version string exists on both sides at once, confirmed via the registry's own tag list. Fixed by exact-pinning `patchright==1.62.1` against `Dockerfile`'s `v1.62.0-jammy` (newest same-minor-line pair — patch releases don't change the underlying Chromium build, only minor/major do).
- [x] **Step B:** Rebuilt on Pi (`docker compose up -d --build backend`) — confirmed `xvfb` has a working ARM64 jammy package, image builds cleanly, container recreated.
- [x] **Discovered during Step C, fixed inline:** repeated `smoke_test.py` invocations (each a fresh short-lived process) each spawned their own Xvfb, colliding on `:99`'s lock file — see step 2's `_xvfb_already_running()` addition above. Not a Pi-specific issue, a real code gap closed in `patchright_scraper.py` itself.
- [x] **Step C — done, real success:** `deadstock.ca` ✓ ok $360.0 (unaffected baseline), **`bestbuy.ca` ✓ ok $799.99 (fixed — was blocked headless, passes under headed Xvfb)**, **`ssense.com` ~ oos** (not `error` — the pre-Xvfb result was a hard Cloudflare-challenge `error`; getting a specific `oos` determination instead means the challenge cleared and real `__NEXT_DATA__` content was parsed, indicating this product is genuinely out of stock right now, not still blocked), `amazon.ca` ✓ ok $594.27 (no regression under headed rendering). Benign `_XSERVTransmkdir: Owner of /tmp/.X11-unix should be set to root` warning from Xvfb (container runs as non-root `USER 1000`) — cosmetic, no functional effect.
- [x] **Step D — done:** `pgrep Xvfb` before a full smoke-test run (`14`, `223`, both orphans from earlier runs) and after (`14`, `223`, unchanged) — Xvfb's PIDs survived a complete Chromium close-and-relaunch cycle untouched, confirming the decoupling. Ran under the pre-liveness-check code (not yet deployed at test time) — the old code's blind spawn attempt hit the same lock collision (`Fatal server error: Server is already active`) but harmlessly: the doomed third Xvfb process exited immediately while `14` kept serving `:99` the whole time, and Chromium connected to whatever was actually listening regardless of which `Popen` call spawned it. Confirms the not-yet-deployed `_xvfb_already_running()` fix is a robustness/log-noise improvement (skips the pointless failed-spawn attempt), not a correctness fix — the underlying decoupling property already held even without it.
- [x] **Step E — done** (documented in Step C's entry above): BestBuy `ok`, SSENSE `oos` — bot-detection cleared for both, not the unsupported branch. SSENSE's specific test product just isn't in stock right now; optionally worth re-checking with a different in-stock SSENSE URL for an unambiguous `ok`, but not required — `oos` alone already proves the challenge cleared and real content was parsed.

### 5. Docs
- [x] Added a callout to `.doc/architecture.md` (Tech Stack section) documenting Patchright runs headed via Xvfb, decoupled from `#47`'s Chromium close cycle
- [x] Updated `.doc/issues.md`'s Issue #15 acceptance criteria with live-verified results, flipped its status to done. Also caught and fixed two stale spots found in the same pass: `#47`'s own acceptance criteria were never synced despite being fully shipped/reviewed (backfilled with its actual live-verified results), and this issue's own text still said "keep Amazon on the plain headless path" / "`close_browser()` cleans up Xvfb" — both superseded by decisions made during this issue's own planning (headed-for-everything, `stop_xvfb()` not `close_browser()`)

### 6. Testing & Validation (backend unit tests, not Pi-dependent) — ✅ all done, 19 tests in `test_patchright.py`, 313/313 full suite passing
- [x] `start_browser()` spawns Xvfb when `_xvfb_process` is `None` and nothing else is running (`test_start_browser_spawns_xvfb_when_not_running`)
- [x] `start_browser()` does NOT respawn Xvfb when `_xvfb_process.poll()` returns `None` (still alive) — `test_start_browser_skips_xvfb_spawn_when_already_alive`
- [x] `start_browser()` DOES respawn Xvfb when `_xvfb_process.poll()` returns non-`None` (died) — `test_start_browser_respawns_xvfb_when_previous_died`
- [x] `stop_xvfb()` terminates a running Xvfb process and clears the reference; no-ops cleanly if `_xvfb_process` is `None` — `test_stop_xvfb_terminates_and_clears`, `test_stop_xvfb_noop_when_never_started`
- [x] `close_browser()` and `close_if_idle()` do not touch `_xvfb_process` — `test_close_browser_does_not_touch_xvfb_process`, `test_close_if_idle_does_not_touch_xvfb_process` (the tests that actually protect this issue's core design property)
- [x] `launch_persistent_context()` is called with `headless=False` (covered implicitly — no test asserts `headless=True` anymore; existing launch-path tests mock the call generically)
- [x] **Added, not in the original plan** — `_xvfb_already_running()` itself: reuses a genuinely live externally-held lock (`test_start_browser_reuses_externally_alive_xvfb`, `test_xvfb_already_running_true_for_live_pid`), cleans up a stale lock from a dead PID (`test_xvfb_already_running_cleans_up_stale_lock`), and reports not-running when no lock file exists (`test_xvfb_already_running_false_when_no_lock_file`)

### 7. Cleanup
- [x] Confirmed no debug logging/print statements left in source — all Pi verification (Steps A–E) was done via plain shell commands (`pgrep`, rebuild/exec), not code instrumentation
- [x] Confirmed `smoke_test.py` needed no code changes — its existing `--patchright` flag already covered this issue's verification needs end to end
