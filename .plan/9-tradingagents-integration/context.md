# Issue #9: Context

## Issue Description

From `.doc/issues.md#L586-643`: wire TradingAgents (https://github.com/TauricResearch/TradingAgents) into `AnalysisConsumer` (replacing the pending-only stub from #7) and expose a manual trigger endpoint. Also expose version-check and update endpoints for the vendored `/opt/tradingagents` clone.

Original acceptance criteria carry over unchanged except where noted in "Target State" below — the mechanism for running TradingAgents headlessly had to be redesigned; the observable behavior (pending → running → done/failed, 409 on overlap, follow-up push, 30-min timeout) is the same.

## Component / Route Summary

### Current State

- `app/consumers/analysis.py` — stub. On `STOCK_THRESHOLD` with `run_analysis=true`, creates an `AnalysisResult(status="pending")` and stops. Nothing ever moves it past `pending`.
- `app/api/stocks.py::analyze_stock_alert` — same stub behavior via the manual-trigger route. Creates the pending row, returns it, nothing runs.
- `app/models/analysis_result.py` — has `action`, `price_target`, `stop_loss` columns, none ever populated.
- `app/models/stock_alert.py` — has `run_analysis: bool` only; no way to configure how an analysis run behaves per ticker.
- No `services/trading_agents.py`, no `app/api/analysis.py`, no TradingAgents clone or venv on the host yet.
- `docker-compose.yml` backend service has no volume mount for `/opt/tradingagents`.

### Target State — and why it differs from the original issue text

The issue spec says: *"Spawns `python run.py --ticker {ticker}` via `asyncio.create_subprocess_exec`... Captures stdout, parses structured JSON output."* This is not how TradingAgents' CLI works.

**Investigated against the actual upstream source** (`cli/main.py`, `cli/utils.py`, `tradingagents/graph/trading_graph.py`, `tradingagents/default_config.py`, `tradingagents/agents/schemas.py` — fetched from `TauricResearch/TradingAgents` on GitHub):

- `cli/main.py`'s `analyze` command runs `get_user_selections()`, an interactive `questionary` wizard. **Ticker, analysis date, and analyst-team selection have no environment-variable bypass** — they are hard `questionary.text()`/`questionary.checkbox()` prompts requiring a real TTY. There is no CLI flag interface at all (`@app.command() def analyze(checkpoint, clear_checkpoints)` — no `--ticker`).
- Everything else (`llm_provider`, `deep_think_llm`, `quick_think_llm`, `backend_url`, `output_language`, `max_debate_rounds`, `max_risk_discuss_rounds`, `anthropic_effort`, etc.) *is* skippable via `TRADINGAGENTS_*` env vars, applied to `DEFAULT_CONFIG` at import time via `_apply_env_overrides()` in `default_config.py`. But that doesn't help — the wizard still blocks on ticker/date/analysts first.
- The underlying **library is fully programmatic**, independent of the CLI wizard: `TradingAgentsGraph(selected_analysts=[...], config=DEFAULT_CONFIG).propagate(ticker, trade_date)` returns `(final_state, decision)` with zero interactivity. The CLI wizard is a UX layer on top of this; we don't need it.
- `decision` is a plain rating string (`Buy`/`Overweight`/`Hold`/`Underweight`/`Sell`, from `SignalProcessor.process_signal`). The structured `PortfolioDecision` object (`rating`, `executive_summary`, `investment_thesis`, `price_target`, `time_horizon`) is rendered to markdown (`final_state["final_trade_decision"]`) and never exposed as a dict through the public API — `price_target` must be regex-extracted from the `**Price Target**: X` line. **There is no `stop_loss` field anywhere in TradingAgents' output.**

**Resulting design change:** a new file we own, `backend/scripts/run_tradingagents.py`, imports the library directly and calls `.propagate()` — it does not shell into `cli/main.py` at all. `services/trading_agents.py` subprocesses *that* script instead of TradingAgents' own entrypoint.

**Execution environment:** the backend container is `linux/arm64` and doesn't have TradingAgents' deps (langgraph, yfinance, questionary, etc.), and `/opt/tradingagents` is a runtime volume mount (not baked into the image), so build-time `pip install` isn't possible. Decision: a host-managed venv at `/opt/tradingagents/.venv` (built once manually on the Pi), mounted in alongside the code. The backend execs that venv's `python` directly rather than the container's own interpreter. `POST /api/analysis/tradingagents/update` re-runs `pip install -r requirements.txt` in that venv right after `git pull`, so it never drifts from what's cloned.

**Config split (per user decision):** `llm_provider` and `output_language` are global, set once via `.env` (`TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_OUTPUT_LANGUAGE`) since they're expected to never vary. `deep_think_llm`, `quick_think_llm`, `anthropic_effort`, `max_debate_rounds`, `max_risk_discuss_rounds`, and `analysts` are per-alert — new nullable columns on `StockAlert`, editable via the existing `POST`/`PATCH /api/stocks` routes. Null means "inherit the global env default" — the subprocess env is only overridden per-field when the alert has a non-null value set.

**`AnalysisResult.stop_loss` is dropped** (migration) rather than left permanently null — nothing in TradingAgents' output can ever populate it.

**Report file location surfaced too:** `TradingAgentsGraph.save_reports(final_state, ticker)` is a public library method explicitly meant for programmatic callers ("Programmatic callers get the same on-disk reports the CLI produces") — it writes the same markdown report tree the interactive CLI writes when you answer "Save report? Y". The wrapper calls this and the resulting path is stored on `AnalysisResult.report_path` (new column), pointing at `/opt/tradingagents/data/reports/<ticker>_<timestamp>/` — inside the already-mounted volume, so it's stable across container restarts and directly browsable on the Pi host.

## Impact & Risk

### Files Changed
- **`backend/scripts/run_tradingagents.py`** (new) — our library-direct wrapper; runs under the host venv's Python, not the backend container's.
- **`backend/app/services/trading_agents.py`** (new) — `run_analysis()`: spawns the wrapper subprocess, applies 30-min timeout with kill, parses stdout JSON, updates `AnalysisResult`, fires the follow-up push.
- **`backend/app/api/analysis.py`** (new) — `GET /api/analysis/tradingagents/version`, `POST /api/analysis/tradingagents/update`.
- **`backend/app/consumers/analysis.py`** — full wiring: flush for `AnalysisResult.id`, spawn `run_analysis()` as a background task.
- **`backend/app/api/stocks.py`** — `analyze_stock_alert` also spawns `run_analysis()` after creating the pending row.
- **`backend/app/models/stock_alert.py`** — 6 new nullable columns.
- **`backend/app/models/analysis_result.py`** — drop `stop_loss`, add `report_path`.
- **`backend/app/schemas/stock_alert.py`**, **`backend/app/schemas/analysis_result.py`** — mirror the model changes.
- **`backend/app/core/config.py`** — `tradingagents_path`, `tradingagents_venv_python` settings (avoid hardcoded paths in service code).
- **`backend/alembic/versions/0006_stock_alert_tradingagents_config.py`** (new migration).
- **`backend/app/main.py`** — mount the new `analysis` router.
- **`docker-compose.yml`** — add `/opt/tradingagents:/opt/tradingagents` volume mount to the `backend` service.
- **`.env.example`** — `ANTHROPIC_API_KEY`, `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_OUTPUT_LANGUAGE`.
- **`.doc/api.md`** — document new `StockAlert` fields, new `/api/analysis/*` routes.

### Dependencies
- **`app/consumers/dispatcher.py`** — unaffected; still runs `analysis.handle()` in its own session per event, phase-isolated from `notify`.
- **`app/services/notifications.py::send_alert`** — reused as-is for the completion push; no changes needed.
- **`app/models/event.py`** — unaffected; `STOCK_THRESHOLD` payload shape (`alert_id`, `ticker`, `price`, `target_price`, `direction`) already carries what's needed.

### New Dependencies
- None in `backend/requirements.txt` — TradingAgents' Python deps live entirely in the separate host venv, never installed into the backend container. This is the whole point of the host-venv decision: zero dependency-conflict surface with FastAPI/SQLAlchemy.
- Host-side, out of band: `/opt/tradingagents` git clone + `/opt/tradingagents/.venv` (manual one-time setup, documented in challenges.md — not something this issue's code can automate on first run).

### Breaking Changes
- `AnalysisResult.stop_loss` column removal is a breaking schema change for anything reading that field (nothing does yet — issue #10's dashboard doesn't exist). Safe now, would not be safe post-#10 without also updating the frontend type.
