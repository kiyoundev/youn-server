# #15: Context

## Issue Description

`PatchrightScraper.start_browser()` launches Chromium `headless=True` unconditionally. Testing (both historical and re-verified this session) found BestBuy (Akamai Bot Manager) and SSENSE (Cloudflare JS challenge + Riskified) both block headless Chromium with a 403/challenge page, but pass cleanly through a real headed browser on the same machine — confirming this is headless-detection, not a network/TLS-level block (which would affect headed and headless identically, and doesn't). Amazon, previously needing a warm-up-navigation workaround, now passes headless with no special handling as of this session's separate Playwright version bump (`v1.44.0-jammy` → `v1.61.0-jammy`).

Production is a Raspberry Pi 4B 8GB running Docker, on Pi OS Lite — no display server (X11/Wayland) at all, not just "no monitor plugged in." `headless=False` cannot run as-is on that image; Chromium needs a display to render into, real or virtual. Xvfb (X virtual framebuffer) provides that virtual display — Chromium connects to it over the ordinary X11 protocol and has no way to distinguish it from a real screen, so it runs genuinely real headed rendering, just into memory instead of a physical monitor. Bot detectors see a genuinely headed browser, because it is one.

Full acceptance criteria: see `.doc/issues.md` → Issue #15.

## Design decisions confirmed this session (via `/grill-me`)

- **Xvfb lifecycle is fully decoupled from Chromium's.** Under `#47` (shipped, superseding `#40`'s original persistent-until-daily-recycle model), `start_browser()`/`close_browser()` now cycle far more often — every `poll_prices` batch and every ad-hoc add batch that drains, via `close_if_idle()`. Xvfb holds no session state to go stale (unlike Chromium's profile-adjacent process state), so tying it to that same frequent cycle would mean needless subprocess churn for zero benefit. Xvfb gets its own classvar (`_xvfb_process`), started lazily inside `start_browser()` (sharing `_start_lock`, liveness checked via `.poll() is None`), and stopped only by a new `stop_xvfb()` classmethod called from `main.py`'s `lifespan` real-shutdown block — never from `close_browser()` or `close_if_idle()`. In this deployment, real shutdown only ever happens on a manual restart or a git-pull-triggered redeploy — never something the app does to itself — so once started, Xvfb runs continuously for the app's entire uptime between restarts (could be days/weeks), which is fine given its own ~30MB footprint.
- **`headless=False` unconditionally, one shared `_context` for all Patchright traffic** — not a per-retailer headed/headless branch. Considered carving Amazon (confirmed passing headless already) onto a separate headless-only path to avoid paying Xvfb's overhead for traffic that doesn't need it; rejected as unneeded complexity (two separate browser-context management paths) for a cost saving that doesn't matter at this app's scale (Xvfb's ~30MB is trivial next to Chromium's own already-accepted footprint, and it's shared across all Patchright traffic once started regardless of who triggered the first launch).
- **Pi-side execution split**: matches this project's established ops-issue pattern (`#13`, `#40`) — the user runs Docker builds and live smoke tests on the actual Pi hardware themselves and reports results back; this plan's job is the code changes (Dockerfile, `patchright_scraper.py`) and clear step-by-step instructions for what to run/verify at each stage, not attempting Pi access directly.
- **"Mark unsupported" fallback stays in the acceptance criteria**, but is not expected to trigger — prior real-display headful testing (this session) already passed cleanly for both BestBuy and SSENSE, strong evidence the block is specifically headless-detection and Xvfb's genuinely-headed rendering should resolve it the same way. Kept as the documented fallback path in case Xvfb's rendering differs from a real physical display in some way that resurfaces the block, not because it's considered likely.

## Component / Route Summary

### Current State
- `PatchrightScraper` (`backend/app/services/scraper/patchright_scraper.py`): `start_browser()` launches `headless=True` unconditionally; `close_browser()` tears down `_context`/`_playwright`; `close_if_idle()` (from `#47`) closes only when `_active_scrapes == 0`, shared by `poll_prices` and `#41`'s ad-hoc batches, holding `_start_lock` across the check-and-close to prevent a double-close race.
- `backend/Dockerfile`: based on `mcr.microsoft.com/playwright/python:v1.61.0-jammy`; no `xvfb` package installed; no `DISPLAY` env var set anywhere.
- `main.py`'s `lifespan`: calls `PatchrightScraper.close_browser()` once, at real app shutdown — the only place that fires on a genuine "the app process is stopping" event (manual restart or a git-pull redeploy), never from anything the app does to itself mid-run.
- `smoke_test.py --patchright`: exercises `HTTPScraper` against Shopify/BestBuy/SSENSE URLs and `PatchrightScraper`/`AmazonCAScraper` against the same set plus a real Amazon product page; supports `--headful` (spins up its own separate non-persistent headed context, bypassing `PatchrightScraper.start_browser()` entirely) and `--debug` (extra signal-probing output) flags already, useful for this issue's live Pi verification.

### Target State
- `PatchrightScraper` gains a class-level `_xvfb_process: subprocess.Popen | None = None`.
- `start_browser()`, inside its existing `_start_lock` block, spawns Xvfb (`Xvfb :99 -screen 0 1920x1080x24`, sets `DISPLAY=:99`) if not already running (`_xvfb_process is None or _xvfb_process.poll() is not None`), *before* calling `launch_persistent_context()`. The `launch_persistent_context()` call itself flips from `headless=True` to `headless=False`.
- New `PatchrightScraper.stop_xvfb()` classmethod, called once from `main.py`'s `lifespan` shutdown block, alongside the existing `close_browser()` call — kills `_xvfb_process` if running, clears the reference.
- `backend/Dockerfile` installs `xvfb` via apt, merged into the existing `python3-venv` install line (per the issue's own note, to avoid an extra image layer).
- `.doc/architecture.md` gets a short note (if it doesn't already reflect this) that Patchright's browser runs headed under a virtual display, not truly headless.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/patchright_scraper.py`** — add `_xvfb_process`, Xvfb spawn logic in `start_browser()`, new `stop_xvfb()`, flip `headless=True` → `headless=False`.
- **`backend/Dockerfile`** — add `xvfb` to the apt install line.
- **`backend/app/main.py`** — add `PatchrightScraper.stop_xvfb()` call in `lifespan`'s shutdown block, alongside the existing `close_browser()` call.
- **`.doc/architecture.md`** — note on Patchright's headed-via-Xvfb rendering, if the existing text implies pure headless.
- **`backend/tests/scraper/test_patchright.py`** — new tests for Xvfb start/liveness-check/stop, and confirming `close_if_idle()`/`close_browser()` don't touch `_xvfb_process`.

### Dependencies
- **`#40`/`#47`** — this issue builds directly inside `start_browser()`/`close_browser()`'s existing lazy-launch, lock-guarded shape; no changes to that shape itself, only additions alongside it.
- **`smoke_test.py`** — used as-is for Pi-side live verification (no code changes needed there), via its existing `--patchright` and `--debug` flags.
- **`main.py`'s `lifespan`** — gains one new call; no structural change to the shutdown sequence's ordering otherwise.

### New Dependencies
- **`xvfb`** (apt package, Debian/Ubuntu) — standard, widely-packaged X virtual framebuffer utility. Expected to have a prebuilt ARM64 build for jammy (it's a common cross-architecture utility), but unconfirmed until the Dockerfile actually builds on the Pi — flagged as a verification step, not assumed.

### Breaking Changes
None externally — internal-only change to `PatchrightScraper`'s browser-launch mode and the Dockerfile's installed packages. No API contract, request/response shape, or DB schema changes. The one behavior change with external-ish effect: Patchright-routed scrapes (currently just `amazon.ca`, plus anything cached as `scraper_type: "patchright"`) render via a real (virtual-display) headed browser instead of headless — expected to be strictly more capable at extracting prices from bot-detection-guarded sites, not less, given this session's own headful test results.
