# #15: Challenges & Notes

## Potential Challenges

1. **ARM64 `xvfb` package availability.** ✅ **Resolved, non-issue** — `apt-get install xvfb` succeeded cleanly on Pi's real ARM64 image, no special handling needed.

2. **Xvfb readiness timing — Chromium connecting before Xvfb has finished binding.** ✅ **Resolved, no fix needed** — every live Pi run succeeded on the first attempt with no added delay between spawning Xvfb and launching Chromium. Xvfb binds fast enough in practice; no readiness pause was ever added.

3. **Confirming Xvfb truly never restarts under `close_if_idle()`'s much higher cycling frequency.** ✅ **Confirmed live, and more thoroughly than planned.** `pgrep Xvfb` before and after a full Chromium close-and-relaunch cycle returned identical PIDs (`14`, `223`). Additionally surfaced a real gap while testing this: `_xvfb_process` is process-local memory, so a standalone script (`smoke_test.py`) invoked more than once against the same long-lived container has no memory of an Xvfb it spawned in a prior invocation — each fresh run tried to spawn its own, colliding with the still-alive original on `:99`'s lock file (`Fatal server error: Server is already active`). Fixed with `_xvfb_already_running()`, a lock-file-based liveness check (reads the holder PID, verifies via `os.kill(pid, 0)`, cleans up a stale lock from a dead PID). Notably, this collision was cosmetically noisy (a scary error line) but never actually broke anything — the doomed duplicate spawn attempt exited immediately while the original Xvfb kept serving `:99` throughout, and Chromium connected to whatever was actually listening regardless of which `Popen` call spawned it. The fix eliminates the noise/wasted spawn attempts; it was not fixing a functional break. Not a production concern either way — one continuous process there has no cross-invocation gap to hit this in the first place.

4. **BestBuy/SSENSE could still block despite genuinely-headed rendering.** ✅ **Resolved — both cleared.** BestBuy: `ok $799.99` (was hard-blocked headless). SSENSE: `oos` (not `error`) — the pre-Xvfb result was a hard Cloudflare-challenge failure with no real content; getting a specific out-of-stock determination instead means the challenge cleared and real `__NEXT_DATA__` content was parsed — this test product just happens to be out of stock right now, not still blocked. Neither hit the "mark unsupported" fallback.

5. **Xvfb-spawned Chromium crashing or hanging without Xvfb itself dying.** Not directly exercised live (no Chromium crash occurred during testing) — remains a reasoned-through, not empirically-verified, expectation. Left as documented behavior rather than a gap, since it follows directly from the decoupling already confirmed in #3 above: `close_browser()` never referencing `_xvfb_process` holds regardless of *why* a close happens (normal `close_if_idle()` drain vs. an unexpected crash both go through the same code path).

## Key Differences

| Aspect | Before (`#40`/`#47`, no Xvfb) | After (`#15`) |
|--------|-------------------------------|------------------|
| Chromium launch mode | `headless=True`, always | `headless=False`, always — via Xvfb |
| Display requirement | None (headless needs no display) | Xvfb virtual framebuffer, `DISPLAY=:99` |
| BestBuy / SSENSE | Blocked (headless-detected) | Confirmed passing live — BestBuy `ok`, SSENSE `oos` (genuine stock status, not blocked) |
| Amazon | Already passes headless (unrelated version-bump fix) | Unaffected — same shared headed context now, was already working |
| New subprocess | None | `Xvfb` process, started lazily on first Patchright use |
| Xvfb lifecycle vs. Chromium's | N/A | Fully decoupled — Xvfb survives every `close_if_idle()` cycle, dies only at real app shutdown |
| Dockerfile packages | `python3-venv` only | `python3-venv xvfb` |

## Rollback Plan

1. Revert `backend/app/services/scraper/patchright_scraper.py`, `backend/Dockerfile`, and `backend/app/main.py` to their pre-change state (`git checkout` or manual revert — no branch exists to simply not-merge, per this project's direct-to-`main` workflow).
2. Revert any `.doc/architecture.md` note added.
3. Rebuild and redeploy (`docker compose up -d --build backend`, both locally and on the Pi).
4. Verify: app starts cleanly, Amazon/Shopify (already-working paths) are unaffected, BestBuy/SSENSE return to their pre-issue blocked state (expected — this is a revert, not a partial fix).

No data/schema involved — trivially revertible, no migration or backfill concerns. If BestBuy/SSENSE are marked `scraper_type=null`/removed from `RETAILER_MAP` as part of this issue's own "unsupported" fallback, that's a separate, independently-revertible data change (existing `Listing` rows), not tied to the code rollback above.
