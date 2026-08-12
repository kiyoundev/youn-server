# Issue #17: Challenges & Notes

## Potential Challenges

1. **stderr buffering could silently defeat the whole mechanism.** `logging.StreamHandler.emit()` flushes per record by default, so routing heartbeats through `logging.info()` (not raw `print()`) should be safe without an explicit `flush=True`. This is an assumption carried over from design discussion, not yet verified against a real run — confirm with the manual end-to-end test in [implementation.md](implementation.md#4-testing--validation) before considering this done. If it turns out buffered, the fix is a forced `handler.flush()` call per heartbeat.

2. **Single-attempt API stall can eat most of the idle-timeout budget.** The Anthropic SDK's default per-attempt read timeout is 600s, unmodified by this issue (see [context.md](context.md#breaking-changes)). A single stalled attempt near that ceiling — before any retry/backoff even happens — could consume most of the 10-minute idle window, risking a false-positive `idle_timeout` kill on a call that would've succeeded on retry. Not fixed here: doing so requires patching the external TradingAgents library's `default_config.py::_ENV_OVERRIDES` to accept `TRADINGAGENTS_TIMEOUT`/`TRADINGAGENTS_MAX_RETRIES`, out of scope for this repo. Mitigation if it bites in practice: watch for `idle_timeout` failures on runs that plausibly would've finished, and file a follow-up against the TradingAgents fork.

3. **Hard-cap and idle-timeout can't distinguish "almost done" from "stuck in a non-terminating loop."** A run hitting the 2h hard cap is known to have been actively producing heartbeats the whole time (idle-timeout would've fired first otherwise) — but whether it was close to finishing or cycling through a debate round that never satisfies its exit condition is not observable from LLM-call-level heartbeat alone. This is an accepted, inherent limit of the chosen design (see issue's own investigation into per-agent visibility), not a bug to fix here.

4. **Non-deadlocking concurrent read is new territory for this codebase.** `_drain_stdout` / `_watch_stderr` running as separate `asyncio.Task`s is the first place this backend reads two subprocess pipes concurrently instead of via `communicate()`. Get the cancellation/cleanup path right — if the hard-cap or idle-timeout branch kills the process, `stdout_task` must still be awaited (it'll hit EOF immediately after kill) rather than left as an unretrieved-exception dangling task, matching the same pitfall the existing `spawn()` helper's docstring already warns about for the outer task.

5. **Existing test fixture (`_fake_process`) needs a full rewrite, not an extension.** All 6 existing `run_analysis` tests currently depend on `process.communicate()` being called; every one of them breaks once that call is removed. This is expected churn, not a regression risk, but it means the whole test file gets touched, not just new test cases appended.

## Key Differences

| Aspect | Current (#9) | Target (#17) |
|--------|---------------|----------------|
| Timeout model | Flat 30 min total elapsed, regardless of activity | 10 min idle (no heartbeat) + 2h hard cap (regardless of heartbeat activity) |
| Subprocess read | `asyncio.wait_for(process.communicate(), timeout=...)` — blocks until exit | Two concurrent tasks: `stdout.read()` to EOF, `stderr.readline()` loop with per-line idle timeout |
| Progress visibility | None — `status="running"` until it finishes or times out | `llm_calls`, `tokens_in`, `tokens_out`, `tool_calls`, `last_heartbeat_at` updated live via API |
| Failure detail | `status="failed"`, reason only in server logs | `error_reason` ∈ {`idle_timeout`, `subprocess_error`, `invalid_output`, `max_runtime_exceeded`} |
| Timeout config | Hardcoded module constant `_TIMEOUT_SECONDS` | `Settings` fields, overridable via env/`.env` without redeploy |

## Rollback Plan

1. Revert the PR (single squash-mergeable branch — no data migrations depend on external state beyond the new nullable/defaulted columns).
2. Run `alembic downgrade -1` to drop the 6 new `analysis_results` columns if rolling back past the migration; not required if only reverting application code (new columns are additive and unused by old code paths).
3. Verify `run_analysis` reverts to `_TIMEOUT_SECONDS`-based `communicate()` behavior — confirm via the pre-existing test suite (`test_trading_agents.py` at the pre-#17 commit) passing again.
4. No in-flight `AnalysisResult` rows need manual intervention — a mid-deploy restart already orphans running analyses under the current design (existing known limitation, not introduced by this issue).
