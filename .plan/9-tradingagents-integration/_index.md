# Issue #9: TradingAgents Integration

## PR / Branch
- **Branch:** `feature/9-tradingagents-integration`
- **PR Title:** `main | feature - 9 - TradingAgents integration`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
<!-- From issue acceptance criteria (.doc/issues.md#L586-643), adjusted for the corrected architecture -->
- [ ] `POST /api/stocks/{id}/analyze` returns 201 immediately; `AnalysisResult.status` transitions `pending → running → done`
- [ ] `POST /api/stocks/{id}/analyze` returns 409 if analysis already running for that ticker
- [ ] `GET /api/stocks/{id}/analysis` returns completed results with non-null `result` JSON and non-null `report_path` pointing at the on-disk markdown report tree
- [ ] `AnalysisConsumer` creates and runs analysis when `run_analysis = true` on a `STOCK_THRESHOLD` event
- [ ] `AnalysisConsumer` skips silently when `run_analysis = false`
- [ ] Follow-up Pushover push sent on analysis completion (separate from the immediate threshold alert from #7)
- [ ] Subprocess timeout of 30 minutes — kills the process and sets `status = "failed"` on timeout
- [ ] `/opt/tradingagents` path missing → `status = "failed"` with error logged, no crash
- [ ] `GET /api/analysis/tradingagents/version` returns correct `behind_count` and `update_available`
- [ ] `POST /api/analysis/tradingagents/update` runs `git pull` + venv `pip install -r requirements.txt`, returns new commit hash
- [ ] Per-alert `deep_think_llm` / `quick_think_llm` / `anthropic_effort` / `max_debate_rounds` / `max_risk_discuss_rounds` / `analysts` are settable via `POST`/`PATCH /api/stocks` and honored by the subprocess run
- [ ] Null per-alert fields fall back to the global `.env` defaults (or the library's own defaults)

## Estimated Effort
- Implementation: **8 hours**
- Testing: **2 hours**
- **Total: 10 hours**

(Original issue estimate was ~5h; scope expanded after discovering TradingAgents' CLI is non-headless — see [context.md](context.md) for what changed and why.)


## Commit Message

Add: TradingAgents subprocess integration (issue #9)

Why:
Automates trade analysis via TradingAgents when a stock alert's
price threshold fires, instead of leaving AnalysisResult rows
stuck pending. TradingAgents' own CLI is an interactive wizard
with no headless path, so this calls the library directly through
a purpose-built wrapper script and subprocess boundary.

How:
- Add 'run_tradingagents.py' wrapper: calls TradingAgentsGraph
  directly, extracts price_target/executive_summary via regex
  from rendered markdown, writes report files, prints one JSON
  line to stdout (all logging routed to stderr)
- Add 'trading_agents.py' service: spawns the wrapper as a
  tracked background asyncio.Task, 30-min timeout with kill,
  per-alert env overrides, catch-all exception guard so a stuck
  subprocess can never leave a row wedged at status=running
- Wire 'consumers/analysis.py' and 'api/stocks.py' analyze route
  to commit the AnalysisResult row before spawning the background
  task, avoiding a cross-connection visibility race under
  Postgres READ COMMITTED isolation
- Add 'api/analysis.py': version/update endpoints for the vendored
  /opt/tradingagents clone, git+pip subprocess calls bounded by
  timeout (60s git, 300s pip) instead of blocking a request
  indefinitely
- Add 6 nullable per-alert override columns on StockAlert
  (deep_think_llm, quick_think_llm, anthropic_effort,
  max_debate_rounds, max_risk_discuss_rounds, analysts); drop
  AnalysisResult.stop_loss (no data source), add report_path
- Guard StockAlertResponse's CSV-to-list conversion against an
  empty string (POST with analysts=[] previously 500'd on read)
- Add alembic migration 0006 for the schema changes above
- Add docker-compose volume mount and .env vars for the
  TradingAgents host venv and API key
- Add unit tests across services/api/scripts covering timeout,
  non-zero exit, bad JSON, missing path, env-override precedence,
  and the empty-analysts edge case

Tags:
tradingagents, subprocess, alembic-migration