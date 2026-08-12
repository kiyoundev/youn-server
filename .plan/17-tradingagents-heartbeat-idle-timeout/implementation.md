# Issue #17: Implementation

## Steps

### 1. Settings & Migration
- [x] `app/core/config.py` — add `tradingagents_idle_timeout_seconds: int = 600`, `tradingagents_hard_cap_seconds: int = 7200`
- [x] `app/models/analysis_result.py` — add `llm_calls`, `tokens_in`, `tokens_out`, `tool_calls` (int, default 0), `last_heartbeat_at` (nullable datetime), `error_reason` (nullable string)
- [x] `alembic/versions/0008_analysis_result_progress_fields.py` — `add_column` x6, `server_default="0"` for the int counters so existing rows backfill cleanly; `downgrade()` drops all 6
- [x] `app/schemas/analysis_result.py` — mirror the 6 new fields on `AnalysisResultResponse`

### 2. Heartbeat Callback Handler (`run_tradingagents.py`)
- [x] Define `HeartbeatCallbackHandler(BaseCallbackHandler)` — same 4-counter shape as upstream `cli/stats_handler.py::StatsCallbackHandler` (`llm_calls`, `tool_calls`, `tokens_in`, `tokens_out`), plus a stderr log line on every counted event
- [x] `on_llm_start` / `on_chat_model_start` — increment `llm_calls`, log heartbeat
- [x] `on_tool_start` — increment `tool_calls`, log heartbeat
- [x] `on_llm_end` — extract `usage_metadata` (same logic as upstream), accumulate `tokens_in`/`tokens_out` — **no heartbeat log here**, only counters (matches issue's 3-event list; token counts lag by one call, documented in [context.md](context.md))
- [x] Heartbeat log format: `logger.info("HEARTBEAT llm_calls=%d tokens_in=%d tokens_out=%d tool_calls=%d", ...)` — via `logging`, not `print()`, so the existing `StreamHandler` per-record flush behavior applies with no extra `flush=True` needed
- [x] Wire into `main()`: `graph = TradingAgentsGraph(selected_analysts=analysts, config=DEFAULT_CONFIG, callbacks=[handler])`

### 3. Concurrent Read Loop (`trading_agents.py`)
- [x] Remove `_TIMEOUT_SECONDS` module constant
- [x] Add `_parse_heartbeat(line: bytes) -> dict | None` — returns `{"llm_calls": ..., "tokens_in": ..., ...}` if the line contains `"HEARTBEAT"` and parses cleanly, else `None`
- [x] Add `_drain_stdout(process) -> bytes` — `return await process.stdout.read()`
- [x] Add `_watch_stderr(process, result_id, idle_timeout) -> str | None` — loop `asyncio.wait_for(process.stderr.readline(), timeout=idle_timeout)`; on `TimeoutError`, `process.kill()` and return `"idle_timeout"`; on EOF (`b""`), return `None`; on a parseable `HEARTBEAT` line, call `_set_status(result_id, last_heartbeat_at=now, **parsed)`
- [x] Rewrite `_run_analysis()`'s subprocess-wait block: spawn `stdout_task` and `stderr_task`, wrap `stderr_task` in `asyncio.wait_for(..., timeout=hard_cap_seconds)`; on outer `TimeoutError`, kill process, `error_reason="max_runtime_exceeded"`; on `stderr_task` returning `"idle_timeout"`, `error_reason="idle_timeout"`; on clean EOF, proceed to `process.wait()` + existing returncode/JSON-parse checks, setting `error_reason="subprocess_error"` or `"invalid_output"` on those existing failure branches (currently just `status="failed"` with no reason)
- [x] Ensure `stdout_task` is always awaited/cancelled on every exit path (idle-timeout and hard-cap both kill the process — `stdout.read()` will hit EOF right after and complete; don't leave it dangling)

### 4. Testing & Validation
- [x] Rewrite `_fake_process()` fixture in `test_trading_agents.py` — `process.stdout.read = AsyncMock(...)`, `process.stderr.readline = AsyncMock(side_effect=[...])` instead of mocking `communicate()`
- [x] Test: heartbeat line updates `AnalysisResult.llm_calls`/`tokens_in`/`tokens_out`/`tool_calls`/`last_heartbeat_at`
- [x] Test: no heartbeat for `idle_timeout` window → `process.kill()` called, `status="failed"`, `error_reason="idle_timeout"`
- [x] Test: continuous heartbeats past old flat-timeout duration but under hard cap → run completes normally (regression guard for the exact bug #17 fixes)
- [x] Test: continuous heartbeats past hard cap → `process.kill()` called, `error_reason="max_runtime_exceeded"`
- [x] Test: non-zero exit still sets `error_reason="subprocess_error"` (extends existing `test_run_analysis_nonzero_exit_sets_failed`)
- [x] Test: bad JSON still sets `error_reason="invalid_output"` (extends existing `test_run_analysis_bad_json_sets_failed`)
- [ ] Manual test: run one real (or lightly-mocked) TradingAgents invocation end-to-end, confirm `HEARTBEAT` lines actually appear on stderr and are `flush`ed promptly (verify the `logging`-per-record-flush assumption holds in practice, not just in theory)

### 5. Cleanup
- [ ] Confirm no remaining references to the removed `_TIMEOUT_SECONDS` constant
- [ ] Run `pytest backend/tests/services/test_trading_agents.py -v`
- [ ] Run project lint/type-check
