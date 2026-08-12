# Issue #9: Challenges & Notes

## Potential Challenges

1. **Wrapper subprocess must emit clean JSON on stdout, nothing else.** `langgraph`, `httpx`, and other TradingAgents deps may log or print to stdout by default. If anything besides our one `json.dumps(...)` line lands on stdout, parsing in `services/trading_agents.py` breaks silently (or worse, half-parses). Mitigation: `run_tradingagents.py` sets up `logging.basicConfig(stream=sys.stderr)` before any `tradingagents` import, and the parse in `trading_agents.py` should treat *any* stdout that isn't valid single-line JSON as a hard failure (`status="failed"`), not attempt fuzzy recovery.

2. **Host venv ABI compatibility with the container.** `/opt/tradingagents/.venv` is built on the Pi host directly (outside Docker), then read from inside the `linux/arm64` backend container via the volume mount. This should work — same physical machine, same architecture — but hasn't been verified against the container's base image (glibc version, etc.). First manual test after setup should confirm `docker compose exec backend /opt/tradingagents/.venv/bin/python -c "import tradingagents"` actually works before wiring anything else.

3. **`ANTHROPIC_API_KEY` (and any data-vendor keys) must reach the subprocess.** `docker-compose.yml` uses `env_file: .env` for the backend container, so `ANTHROPIC_API_KEY` is already in `os.environ` inside the container — and `run_analysis()` passes `os.environ.copy()` through to the subprocess, so no extra plumbing needed. Worth an explicit manual test regardless (missing/wrong key should fail fast and visibly, not hang).

4. **No structured `price_target`, no `stop_loss` at all.** TradingAgents' public API only returns a rating string and a rendered markdown block; `price_target` is regex-extracted from `**Price Target**: X` in that markdown. If the LLM ever changes the header text (unlikely but it's Anthropic-model-dependent output, not a fixed template we control), the regex silently returns `None` rather than erroring — acceptable since `price_target` is documented as optional in the upstream schema too. `stop_loss` is dropped entirely from `AnalysisResult` (migration) since there's no source for it.

5. **Zombie processes on timeout.** `asyncio.wait_for(process.communicate(), timeout=1800)` raising `TimeoutError` does *not* kill the subprocess by itself — must explicitly `process.kill()` then `await process.wait()` in the `except` block, or the TradingAgents run keeps burning LLM API calls and CPU in the background after we've already marked it `"failed"`.

6. **Background task lifetime.** `asyncio.create_task()`'s return value must be held by a strong reference for the task's lifetime, or it can be garbage-collected mid-run (a well-known asyncio footgun). Neither `analysis.py`'s consumer function nor the `analyze_stock_alert` route naturally holds a long-lived reference across the request/event lifecycle, so `trading_agents.py` needs its own module-level task registry (`_background_tasks: set[asyncio.Task]` + done-callback discard) — this app doesn't have an existing "fire and forget with tracking" utility to reuse; `main.py`'s `dispatch_task` is held directly because it's a single long-lived task, not a pattern for spawning many short-lived ones.

7. **Report directory lives inside the git-managed clone path.** `TRADINGAGENTS_RESULTS_DIR=/opt/tradingagents/data` is a subdirectory of the same `/opt/tradingagents` that `git pull` operates on. It's untracked (not part of upstream's repo), so a plain `git pull` won't touch it — but if anyone ever runs `git clean -fdx` by hand on that host directory, saved reports would be wiped. Worth a one-line note in the host setup docs; not worth engineering around for a single-operator personal server.

8. **Update endpoint installs whatever's on `origin/main`.** Same trust model the issue text already calls out for `git pull` — extending it to also run `pip install -r requirements.txt` means a malicious or broken upstream commit could also introduce a malicious dependency pin. No different in kind from the existing `git pull` trust boundary, just worth naming explicitly since it's new surface (arbitrary `pip install` from a remote-controlled requirements file).

## Key Differences From Original Issue Text

| Aspect | Original Issue (`.doc/issues.md`) | Final Plan |
|--------|-----------------------------------|------------|
| Subprocess target | `python run.py --ticker {ticker}` (TradingAgents' own entrypoint) | Our own `backend/scripts/run_tradingagents.py`, calling the `TradingAgentsGraph` library API directly — TradingAgents' actual CLI (`cli/main.py`) is an interactive `questionary` wizard with no headless path for ticker/date/analysts |
| Execution environment | Implied: same Python env as the backend | Separate host venv at `/opt/tradingagents/.venv`, execed directly — avoids merging TradingAgents' deps into the FastAPI backend's own dependency set |
| Config knobs (provider/models/effort/depth/language) | Not mentioned in the issue at all | Split: `llm_provider` + `output_language` global via `.env`; `deep_think_llm`/`quick_think_llm`/`anthropic_effort`/`max_debate_rounds`/`max_risk_discuss_rounds`/`analysts` per-alert (new `StockAlert` columns) |
| `AnalysisResult.stop_loss` | Existing column, implied populated | Dropped — no data source in TradingAgents' output |
| `AnalysisResult.price_target` | Existing column, implied populated | Populated via regex extraction from rendered markdown (not structured in the public API) |
| Update endpoint | `git pull` only | `git pull` + venv `pip install -r requirements.txt`, so the venv never drifts from the cloned code without a second manual step |

## Rollback Plan
1. Revert the feature branch; `analysis.py`/`stocks.py` stub behavior (pending-only, never progresses) is simple enough to restore from git history.
2. `alembic downgrade -1` if the migration (new `StockAlert` columns + dropped `stop_loss`) causes problems in a deployed DB.
3. Remove the `/opt/tradingagents` volume mount from `docker-compose.yml` and restart if the host venv turns out to be ABI-incompatible inside the container — this fully disables the feature without touching code, since `run_analysis()` already treats a missing path as a handled failure, not a crash.
4. Verify `GET /api/health` and `GET /api/stocks` still respond correctly post-rollback.
