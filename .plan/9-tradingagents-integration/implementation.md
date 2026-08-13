# Issue #9: Implementation

## Steps

### 1. Host setup (manual, outside the codebase)
- [ ] Clone TradingAgents to `/opt/tradingagents` on the Pi (if not already done for a previous manual test).
- [ ] `python -m venv /opt/tradingagents/.venv && /opt/tradingagents/.venv/bin/pip install -r /opt/tradingagents/requirements.txt`.
- [ ] Add `ANTHROPIC_API_KEY`, `TRADINGAGENTS_LLM_PROVIDER=anthropic`, `TRADINGAGENTS_OUTPUT_LANGUAGE=English` to `.env`.

### 2. Data layer
- [ ] `app/models/stock_alert.py` — add 6 nullable columns: `deep_think_llm: Mapped[str | None]`, `quick_think_llm: Mapped[str | None]`, `anthropic_effort: Mapped[str | None]`, `max_debate_rounds: Mapped[int | None]`, `max_risk_discuss_rounds: Mapped[int | None]`, `analysts: Mapped[str | None]` (CSV).
- [ ] `app/models/analysis_result.py` — remove `stop_loss` column, add `report_path: Mapped[str | None]`.
- [ ] Alembic migration `0006_stock_alert_tradingagents_config.py`: `add_column` x6 on `stock_alerts`, `drop_column("analysis_results", "stop_loss")`, `add_column("analysis_results", "report_path")`.
- [ ] `app/schemas/stock_alert.py` — add the 6 fields to `StockAlertCreate`, `StockAlertUpdate`, `StockAlertResponse`. `analysts` as `list[Literal["market","social","news","fundamentals"]] | None` in the API layer; convert to/from the CSV column in the route handlers (small `_analysts_to_csv` / `_csv_to_analysts` helpers, or a computed property on the ORM model — pick whichever keeps `api/stock_alerts.py` free of string-splitting noise).
- [ ] `app/schemas/analysis_result.py` — remove `stop_loss` field, add `report_path: str | None`.
- [ ] `app/core/config.py` — add `tradingagents_path: str = "/opt/tradingagents"`, `tradingagents_venv_python: str = "/opt/tradingagents/.venv/bin/python"`, `tradingagents_results_dir: str = "/opt/tradingagents/data"`.

### 3. TradingAgents wrapper script (new, ours — not part of the vendored clone)
- [ ] `backend/scripts/run_tradingagents.py`:
  - `argparse`: positional `ticker`, `trade_date`; `--analysts` (comma-separated, default `market,social,news,fundamentals`).
  - `logging.basicConfig(stream=sys.stderr, ...)` before importing `tradingagents` — several of its deps log to stdout by default; must be redirected so stdout stays parseable JSON only.
  - `from tradingagents.graph.trading_graph import TradingAgentsGraph` / `from tradingagents.default_config import DEFAULT_CONFIG` — these imports only resolve because the caller sets `PYTHONPATH=/opt/tradingagents` and runs under the host venv's Python.
  - Build `graph = TradingAgentsGraph(selected_analysts=args.analysts.split(","), config=DEFAULT_CONFIG)` — `DEFAULT_CONFIG` already has `TRADINGAGENTS_*` env overrides applied via `_apply_env_overrides()` at import time, so per-alert overrides just need to be set as env vars by the caller before this process starts.
  - `final_state, decision = graph.propagate(args.ticker, args.trade_date)`.
  - Regex-extract `price_target` from `final_state["final_trade_decision"]` (pattern: `\*\*Price Target\*\*:\s*([\d.]+)`) — the structured `PortfolioDecision` object isn't exposed through `propagate()`'s return values, only its rendered markdown.
  - `report_path = graph.save_reports(final_state, args.ticker)` — writes the same markdown report tree the interactive CLI writes (via `write_report_tree`), under `<TRADINGAGENTS_RESULTS_DIR>/reports/<ticker>_<timestamp>/`. `TRADINGAGENTS_RESULTS_DIR` is set by the caller to `/opt/tradingagents/data` so it lands inside the mounted volume rather than some ephemeral container path.
  - `print(json.dumps({...}))` — single line, stdout only, including `"report_path": str(report_path)`. See schema.md for the exact shape.
  - Non-zero `sys.exit(1)` on any exception, with the exception logged to stderr first.

### 4. Service layer
- [ ] `app/services/trading_agents.py`:
  - Module-level `_background_tasks: set[asyncio.Task] = set()` plus a `spawn(coro)` helper that adds the task and registers `task.add_done_callback(_background_tasks.discard)` — needed because `asyncio.create_task()` results must be held by a strong reference or they can be GC'd mid-run; there's no existing app-level task registry to reuse (unlike `dispatch_task`, which `main.py` holds directly).
  - `async def run_analysis(alert: StockAlert, result_id: int) -> None`:
    - Build subprocess env: `os.environ.copy()`, set `PYTHONPATH=settings.tradingagents_path`, `TRADINGAGENTS_RESULTS_DIR=settings.tradingagents_results_dir`, then conditionally set `TRADINGAGENTS_DEEP_THINK_LLM` / `TRADINGAGENTS_QUICK_THINK_LLM` / `TRADINGAGENTS_ANTHROPIC_EFFORT` / `TRADINGAGENTS_MAX_DEBATE_ROUNDS` / `TRADINGAGENTS_MAX_RISK_ROUNDS` only when the corresponding `alert.*` field is not `None` — null fields simply don't override, letting the global `.env` value (already in `os.environ`) pass through untouched.
    - Own `AsyncSession`, set `AnalysisResult.status = "running"` and commit, *before* spawning the subprocess — so a concurrent `GET` sees `running` immediately, not a stale `pending`.
    - Guard: if `not os.path.isdir(settings.tradingagents_path)` → log error, set `status = "failed"`, commit, return — no crash (explicit acceptance criterion).
    - `asyncio.create_subprocess_exec(settings.tradingagents_venv_python, wrapper_script_path, alert.ticker, today_iso, "--analysts", analysts_csv, env=env, stdout=PIPE, stderr=PIPE, cwd=settings.tradingagents_path)`.
    - `asyncio.wait_for(process.communicate(), timeout=1800)` — on `TimeoutError`, `process.kill()`, await `process.wait()`, set `status = "failed"`, commit, return (explicit acceptance criterion: 30-min max).
    - On non-zero exit or JSON-parse failure of stdout → `status = "failed"`, log stderr, commit, return.
    - On success → parse JSON, set `result = <parsed dict>`, `action = parsed["decision"]`, `price_target = parsed.get("price_target")`, `report_path = parsed.get("report_path")`, `status = "done"`, `completed_at = now`, commit.
    - Call `send_alert(title=f"TradingAgents: {alert.ticker} → {parsed['decision']}", body=parsed["executive_summary"][:500])` as a **follow-up** push — separate from the immediate threshold alert `notify.py` already sent for the triggering event.

### 5. Wiring — consumer + manual route
- [ ] `app/consumers/analysis.py`: after `session.add(AnalysisResult(...))`, `await session.flush()` to get `.id` before the function returns (dispatcher commits the session afterward — flush is enough to assign the PK without duplicating the commit). Then `trading_agents.spawn(trading_agents.run_analysis(alert, analysis.id))`.
- [ ] `app/api/stockalerts.py::analyze_stock_alert`: after `await db.commit()` on the new `AnalysisResult`, `trading_agents.spawn(trading_agents.run_analysis(alert, analysis.id))` before `return analysis`.

### 6. New router — version/update
- [ ] `app/api/analysis.py`:
  - `GET /api/analysis/tradingagents/version`: if path missing → `{"available": False}`. Else `git fetch origin` (subprocess, cwd=`/opt/tradingagents`), then `git rev-parse HEAD`, `git rev-parse origin/main`, `git log -1 --format=%cI HEAD`, `git log -1 --format=%cI origin/main`, `git rev-list HEAD..origin/main --count`. Assemble response per schema.md.
  - `POST /api/analysis/tradingagents/update`: `git pull` (cwd=`/opt/tradingagents`) then `<venv>/bin/pip install -r requirements.txt` (cwd=`/opt/tradingagents`) — both via `asyncio.create_subprocess_exec`, combine stdout+stderr into `output`. `git rev-parse HEAD` afterward for `new_commit`.
- [ ] `app/main.py`: `app.include_router(analysis.router, dependencies=[Depends(verify_api_key)])`.

### 7. Deployment config
- [ ] `docker-compose.yml`: add `- /opt/tradingagents:/opt/tradingagents` to the `backend` service's `volumes:`.
- [ ] `.env.example`: `ANTHROPIC_API_KEY=`, `TRADINGAGENTS_LLM_PROVIDER=anthropic`, `TRADINGAGENTS_OUTPUT_LANGUAGE=English`, with a comment noting per-alert overrides go through the API, not `.env`. `TRADINGAGENTS_RESULTS_DIR` is not env-configured by the operator — it's fixed to `/opt/tradingagents/data` in `config.py` since it must stay inside the mounted volume.
- [ ] `.doc/api.md`: document the 6 new `StockAlert` fields, the 2 new `/api/analysis/*` routes, `report_path` on `AnalysisResult`, and remove `stop_loss` from the `AnalysisResult` interface.

### 8. Testing & validation
- [ ] Manual test: `docker compose exec backend /opt/tradingagents/.venv/bin/python -c "import tradingagents"` — confirm the host venv is importable from inside the container before wiring anything else (verifies challenges.md #2, ABI compat).
- [ ] Manual test: blank/bad `ANTHROPIC_API_KEY`, trigger analysis — confirm fast, visible failure (`status = "failed"`, error logged) rather than a hang (verifies challenges.md #3).
- [ ] Manual test: `POST /api/stockalerts/{id}/analyze` on a real alert with `ANTHROPIC_API_KEY` set — confirm `status` goes `pending → running → done` and `result` is populated.
- [ ] Manual test: kill the subprocess mid-run (or set timeout artificially low) — confirm `status = "failed"`, process is actually reaped (no zombie).
- [ ] Manual test: temporarily rename `/opt/tradingagents` — confirm `status = "failed"`, no unhandled exception in logs.
- [ ] Manual test: two overlapping `POST /api/stockalerts/{id}/analyze` calls for the same ticker — second returns 409 (existing unique-index guard from #8, unaffected by this issue).
- [ ] Manual test: `PATCH /api/stockalerts/{id}` with `anthropic_effort=null` after previously setting `"high"` — confirm the next run falls back to the global env default (no per-alert env override applied).
- [ ] Manual test: `GET /api/analysis/tradingagents/version` before and after a manual `git commit` on a test branch upstream (or a stale local clone) — confirm `behind_count` and `update_available` are accurate.
- [ ] Edge case: TradingAgents wrapper script prints non-JSON to stdout (e.g. a stray `print()` from a dependency) — confirm `status = "failed"` rather than a silent wrong-parse.

### 9. Cleanup
- [ ] Remove any debug `print()`/temporary logging added while validating the subprocess contract.
- [ ] Run `pytest` (backend's only configured tooling — no lint/type-check config in `pyproject.toml`) and confirm the existing suite still passes alongside any new tests for `services/trading_agents.py`.

### 10. Post-commit deployment checklist
Code committed (`70ce16e`). Remaining steps to actually run this, in order:

- [x] **Alembic migration** — `alembic upgrade head` run by user, DB now at `0007`.
- [ ] **Deferred to Pi** — Docker recreate, host-side TradingAgents setup, `.env` values, and the end-to-end smoke test are all deferred until the physical Pi arrives (2026-07-02 decision). Full checklist now lives in `.doc/issues.md` Issue #13 (Pi Deployment), already updated with the validated steps. Rationale: the venv has to be rebuilt fresh regardless of host (Mac-built venvs are Darwin binaries, unusable in the Linux container), Docker Desktop's File Sharing permission step is Mac-only friction that won't exist on the Pi's plain Docker Engine, and the biggest remaining cost (installing TradingAgents' full dependency set) is identical either way — so there's little saved by doing it on Mac first, and Pi setup may actually be smoother.
  - Known reusable state for whenever setup happens: an existing working TradingAgents clone already exists at `/Users/youn/Documents/tools/TradingAgents` (tracks `TauricResearch/TradingAgents` upstream, has a working `.env` with a validated `ANTHROPIC_API_KEY`). TradingAgents auto-loads `.env` from its cwd via `python-dotenv`'s `load_dotenv(find_dotenv(usecwd=True))` with `override=False` — so if that folder (or a copy of it) is ever reused as the mount source, its `.env` fills in as a fallback without overriding whatever this project's own root `.env` sets explicitly.
  - Trade-off accepted: the TradingAgents integration (issue #9) stays unvalidated beyond mocked unit tests until the Pi setup happens — no real subprocess/API run has been exercised yet.
