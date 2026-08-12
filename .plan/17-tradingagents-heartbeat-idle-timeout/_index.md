# Issue #17: TradingAgents Progress Heartbeat + Idle Timeout

## PR / Branch
- **Branch:** `feature/17-tradingagents-heartbeat-idle-timeout`
- **PR Title:** `main | feature - 17 - TradingAgents progress heartbeat + idle timeout`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ✅ Done | [review.md](review.md) |

## Success Criteria
- [x] Heartbeat lines appear on stderr during a real run, one per LLM/tool call start (`on_llm_start`, `on_chat_model_start`, `on_tool_start`)
- [x] Idle timer resets on each heartbeat; process is only killed after 10 min of no heartbeat, not flat total elapsed time
- [x] A run that legitimately takes 25+ minutes with continuous heartbeats completes successfully (not killed)
- [x] A genuinely hung subprocess (no heartbeats) is killed within the idle-timeout window
- [x] A run that keeps producing heartbeats but never finishes is killed at the 2h hard cap, with `error_reason="max_runtime_exceeded"` (distinct from `idle_timeout`)
- [x] `AnalysisResult` exposes live progress (`llm_calls`, `tokens_in`, `tokens_out`, `tool_calls`, `last_heartbeat_at`) while `status="running"`
- [x] `AnalysisResult` failure states are distinguishable via `error_reason` (`idle_timeout` / `subprocess_error` / `invalid_output` / `max_runtime_exceeded`), not just `status="failed"`
- [x] Idle-timeout and hard-cap are configurable via `Settings`, not hardcoded constants

## Estimated Effort
- Implementation: **2 hours**
- Testing: **1 hour**
- **Total: 3 hours** (issue estimate was ~2h; revised up after design review surfaced the stdout/stderr concurrent-read rewrite and new migration/settings work)
