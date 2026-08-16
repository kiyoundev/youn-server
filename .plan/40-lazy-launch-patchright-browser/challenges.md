# #40: Challenges & Notes

## Potential Challenges

1. **Duplicate-launch race under concurrent first use** — the core problem this issue solves. Multiple concurrent callers (e.g. `#41`'s bulk-add background scrapes) all seeing `_context is None` simultaneously and racing into separate `launch_persistent_context()` calls. **Mitigated by:** double-checked locking (`_start_lock`) — first caller launches, everyone else blocks on the lock then re-checks and finds `_context` already set.

2. **Recycle-mid-launch race** — surfaced during planning, not in the issue's original spec. If the daily recycle job fires at the exact moment `start_browser()` is mid-launch (a multi-second window), a naive `recycle_browser()` checking `_context is None` could see the not-yet-set value and think there's nothing to recycle, or worse, `close_browser()` a context that's still being constructed. **Resolution:** `recycle_browser()` acquires the *same* `_start_lock` as `start_browser()` before touching `_context` — this serializes recycle against concurrent launches for free, no second lock needed. Low real-world odds (daily cadence vs. a multi-second launch window) but cheap to close off correctly rather than leave as a live gap.

3. **First-use latency** — whichever request is first to actually need Patchright pays the full multi-second browser-launch cost inline, unlike the eager-start design which would have paid it once at app boot instead. Acceptable given this app's non-latency-sensitive scrape cadence (6h scheduled cycles, single user) — but confirm during testing that this doesn't trip any upstream HTTP timeout on whatever endpoint triggered the first real scrape.

4. **Browser crash outside the recycle cycle** — if Chromium crashes unexpectedly (not via the planned daily recycle), `_context` remains set to a stale/broken reference. Nothing currently detects this beyond individual `get_price()` calls' own `try/except` returning `status="error"` repeatedly, until the next scheduled recycle (up to 24h later) happens to fix it by chance. Accepted as a known gap at this app's scale (single user, low request volume) rather than building active health-checking — worth revisiting only if this actually manifests in practice.

5. **`CHROMIUM_PATH` is confirmed dead code** — not a risk to this issue's implementation, but worth recording so it isn't rediscovered as a mystery later: the Dockerfile writes it to `/etc/environment`, which the running `uvicorn` process (PID 1, no login shell) never sources. Verified live that Patchright's own default binary discovery works fine regardless. Left as-is per `implementation.md` step 5 — real cleanup, but out of scope here.

## Key Differences

| Aspect | Original plan (eager) | This plan (lazy + lock) |
|--------|----------------------|--------------------------|
| Browser launch trigger | Unconditionally at app startup | On first real `get_price()` call that needs Patchright |
| Concurrency safety | Avoided by construction (no request traffic yet at startup) | `_start_lock` with double-checked locking |
| Resource cost if never needed | Full persistent browser process runs regardless | Never launches at all |
| Cost paid by first real user | None (already running) | One-time multi-second launch latency |
| Matches `FinnhubClient` pattern | Yes | No — deliberate divergence, justified by Patchright being a minority path (see `context.md`) |

## Rollback Plan

1. Revert `backend/app/services/scraper/patchright_scraper.py` and `backend/app/main.py` to their pre-change state (`git checkout` or manual revert — no branch exists to simply not-merge, per this project's direct-to-`main` workflow).
2. Revert the `.doc/architecture.md` Polling Schedule row.
3. Rebuild and redeploy (`docker compose up -d --build backend`, both locally and on the Pi).
4. Verify: app starts cleanly, existing non-Patchright scrapes (Shopify/JSON-LD/OG/Next.js sites) are unaffected either way, since this change is scoped entirely to `PatchrightScraper`'s own lifecycle.

No data/schema involved — trivially revertible, no migration or backfill concerns.
