# Issue #8: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

Ran `/code-reviewer`. Verdict: Request Changes → all findings fixed and re-verified against real Postgres.

| # | Severity | Finding | Fix | Outcome |
|---|----------|---------|-----|---------|
| 1 | Critical | `verify_api_key` fails open when `API_KEY` is unset (`""`) — empty `X-API-Key` header passes auth | `not settings.api_key` short-circuits to 401; `secrets.compare_digest()` for the actual comparison | Fixed — verified 401 on both empty-header and missing-header cases with empty configured key |
| 2 | Major | `PATCH /api/stockalerts/{id}` direction collision → unhandled `IntegrityError` → 500 | Wrapped commit in `try/except IntegrityError` → 409, matching `create_stock_alert` | Fixed — verified against real DB (two alerts, same ticker, colliding direction → clean 409) |
| 3 | Major | Dead code: `_derive_retailer()` defined but never called; `create_item` duplicated the logic inline | Removed duplication, split into `_hostname_of()` + `_derive_retailer(hostname)`, both actually used | Fixed |
| 4 | Major | TOCTOU race on `POST /api/stockalerts/{id}/analyze`'s "already running" check — app-level check-then-insert, not DB-enforced | Added partial unique index `uq_analysis_results_ticker_running` (`ticker` WHERE `status IN ('pending','running')`) via migration `0005`; wrapped commit in `try/except IntegrityError` → 409 | Fixed — verified at DB level (two pending rows for same ticker → second insert rejected) |
| 5 | Minor | Non-constant-time API key comparison | `secrets.compare_digest()` (bundled with fix #1) | Fixed |
| 6 | Minor | Expensive scraper probe ran before the cheap duplicate-`url` check | Added pre-check `SELECT` before probing; `IntegrityError` catch remains as race-safe backstop | Fixed |
| 7 | Minor | Inconsistent query bounds — `days` had no upper limit while `limit` did | Added `le=365` to `days` | Fixed |
| 8 | Minor | Redundant `finnhub.update_alert()` call when only `run_analysis` changed (Finnhub cache doesn't track that field) | Narrowed the `elif` to only fire when `target_price`/`direction` actually changed | Fixed |

Added 8 new tests covering the fixes (duplicate-direction 409, race-duplicate 409 for both `url` and `/analyze`, empty-key-bypass regression, run_analysis-only no-op). **164 tests passing** (up from 158 pre-review).

Also flagged, not part of this PR: `.claude/settings.local.json` shows as modified on this branch — unrelated MCP tool permissions, pre-existing before this session started.

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
