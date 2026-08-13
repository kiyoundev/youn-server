# Issue #17: Context

## Issue Description

Replace #9's flat 30-minute total-runtime timeout with an idle-timeout driven by real progress signal from the running TradingAgents subprocess, and expose that progress via the API.

**What to build:**
- `backend/scripts/run_tradingagents.py`: a LangChain callback handler (same shape as upstream's `cli/stats_handler.py::StatsCallbackHandler`), passed via `TradingAgentsGraph(..., callbacks=[handler])`. On `on_llm_start` / `on_chat_model_start` / `on_tool_start`, logs one heartbeat line to stderr — stdout stays reserved for the single final JSON line.
- `backend/app/services/trading_agents.py::run_analysis()`: stop using `asyncio.wait_for(process.communicate(), timeout=...)`. Instead, read `process.stderr` incrementally while the process runs. Each heartbeat line resets an idle timer; kill the process only after N minutes with no heartbeat.
- `AnalysisResult`: new fields for live progress (`llm_calls`, `tokens_in`, `tokens_out`, `tool_calls`, `last_heartbeat_at`) updated on each heartbeat.
- `AnalysisResult`: new `error_reason` field so failures are distinguishable via the API instead of a bare `status="failed"`.

**Acceptance criteria:** see [_index.md](_index.md#success-criteria).

**Why:** #9 ships with a flat 30-minute timeout regardless of the alert's own config. A deep/high-effort run (`max_debate_rounds=5`, `max_risk_discuss_rounds=5`, `anthropic_effort="high"`, all 4 analysts) does many more LLM calls than a shallow one and can legitimately approach or exceed 30 minutes (observed ~20 min / 24 LLM calls for a medium-effort manual run). A flat timeout risks killing legitimately-still-working deep runs as false-positive hangs, while wasting most of the budget on shallow ones that finish in minutes.

`TradingAgentsGraph` doesn't expose per-agent progress through its public API outside the CLI's `debug=True` path (which pollutes stdout — incompatible with our clean-stdout-JSON contract). LLM-call-level heartbeat, via `callbacks` (already wired into the LLM client at `trading_graph.py:81`, `llm_kwargs["callbacks"] = self.callbacks`), is what's actually available and is sufficient to prove forward progress.

## Component / Route Summary

### Current State

- `run_tradingagents.py` calls `TradingAgentsGraph(selected_analysts=analysts, config=DEFAULT_CONFIG)` with no callbacks. `logging.basicConfig(stream=sys.stderr, level=logging.INFO)` is already set up (default format `%(levelname)s:%(name)s:%(message)s`).
- `trading_agents.py::_run_analysis()` spawns the subprocess and calls `asyncio.wait_for(process.communicate(), timeout=_TIMEOUT_SECONDS)` — a flat 30-minute (`_TIMEOUT_SECONDS = 30 * 60`) module constant, blocks until exit or timeout with zero visibility in between.
- `AnalysisResult` has `id, stock_alert_id, event_id, ticker, triggered_price, result, status, action, price_target, report_path, created_at, completed_at` — no progress or failure-reason fields. Partial unique index on `(ticker) WHERE status IN ('pending','running')` — a stuck row blocks future analyses for that ticker.
- `AnalysisResultResponse` (Pydantic schema) mirrors the model 1:1; `GET /api/stockalerts/{id}/analysis` (`app/api/stockalerts.py:198`) returns it directly — no route code changes needed once the model/schema gain new fields.
- `Settings` (`app/core/config.py`) holds deployment paths (`tradingagents_path`, `tradingagents_venv_python`, `tradingagents_results_dir`) but no timeout/idle-timeout knobs.
- Existing tests (`test_trading_agents.py`) mock `process.communicate()` as a single `AsyncMock` — this pattern breaks once `communicate()` is no longer called.

### Target State

- `run_tradingagents.py` gains a `HeartbeatCallbackHandler(BaseCallbackHandler)` (same 3-event shape as upstream `StatsCallbackHandler`, plus a stderr log line per event), passed as `TradingAgentsGraph(..., callbacks=[handler])`.
- `_run_analysis()` spawns two concurrent `asyncio.Task`s: one drains `process.stdout` to EOF, one reads `process.stderr` line-by-line with a per-line `asyncio.wait_for(..., timeout=idle_timeout)` — resetting on every line, killing the process on timeout. A separate outer bound (hard cap) wraps the whole watch loop.
- `AnalysisResult` gains `llm_calls`, `tokens_in`, `tokens_out`, `tool_calls` (ints, default 0), `last_heartbeat_at` (nullable timestamp), `error_reason` (nullable string) — updated via `_set_status()` on every heartbeat line.
- `Settings` gains `tradingagents_idle_timeout_seconds: int = 600` and `tradingagents_hard_cap_seconds: int = 7200`.
- `AnalysisResultResponse` gains the same 5 new fields, `from_attributes` handles the rest automatically.

## Impact & Risk

### Files Changed
- **`backend/scripts/run_tradingagents.py`** — add `HeartbeatCallbackHandler`, wire into `TradingAgentsGraph(callbacks=[...])`.
- **`backend/app/services/trading_agents.py`** — replace `communicate()`-based wait with concurrent stdout-drain / stderr-watch tasks; parse `HEARTBEAT` lines and update `AnalysisResult` per line; replace `_TIMEOUT_SECONDS` module constant with `Settings`-driven idle-timeout + hard-cap; set `error_reason` on every failure path (`idle_timeout`, `subprocess_error`, `invalid_output`, `max_runtime_exceeded`).
- **`backend/app/models/analysis_result.py`** — add 6 new columns.
- **`backend/app/schemas/analysis_result.py`** — add the same 6 fields to `AnalysisResultResponse`.
- **`backend/app/core/config.py`** — add `tradingagents_idle_timeout_seconds`, `tradingagents_hard_cap_seconds`.
- **`backend/alembic/versions/0008_analysis_result_progress_fields.py`** (new) — migration for the new columns.
- **`backend/tests/services/test_trading_agents.py`** — rewrite the process fixture to mock `stdout.read()` / `stderr.readline()` instead of `communicate()`; add idle-timeout and hard-cap test cases.

### Dependencies
- **`langchain_core.callbacks.BaseCallbackHandler`** — already a transitive dependency via the TradingAgents library (used by `trading_agents/graph/trading_graph.py` and upstream's own `cli/stats_handler.py`); no new package needed.
- **`app/api/stockalerts.py::list_analysis_results`** — unaffected; returns `AnalysisResultResponse` directly, new fields flow through automatically.
- **`app/consumers/analysis.py::handle`** — unaffected; only creates the initial `pending` row and calls `spawn(run_analysis(...))`.

### Breaking Changes

None to the public API shape — all new fields are additive (nullable or defaulted). `_TIMEOUT_SECONDS` module constant is removed in favor of `Settings` fields; nothing external references it directly (confirmed only used internally in `_run_analysis`).

**Known residual risk (not fixed by this issue, documented for awareness):** the Anthropic SDK client's default per-attempt read timeout is 600s with up to 2 retries (unmodified — `timeout`/`max_retries` aren't currently forwarded to the TradingAgents library's config, and doing so would require patching the external TradingAgents repo's `default_config.py::_ENV_OVERRIDES`, out of scope here). A single stalled attempt near the 600s ceiling could by itself consume close to the entire 10-min idle-timeout budget before any retry/backoff even occurs — theoretically closer to a false-positive `idle_timeout` kill than "3 full attempts" suggests. See [challenges.md](challenges.md).
