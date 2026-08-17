import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.core.background_tasks import spawn  # noqa: F401 — re-exported for callers using trading_agents.spawn(...)
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.models.analysis_result import AnalysisResult
from app.models.stock_alert import StockAlert
from app.services.notifications import send_alert

_log = logging.getLogger(__name__)

_WRAPPER_SCRIPT = str(Path(__file__).resolve().parents[2] / "scripts" / "run_tradingagents.py")
_HEARTBEAT_FIELDS = ("llm_calls", "tokens_in", "tokens_out", "tool_calls")


def _build_env(alert: StockAlert) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = settings.tradingagents_path
    env["TRADINGAGENTS_RESULTS_DIR"] = settings.tradingagents_results_dir
    if alert.deep_think_llm is not None:
        env["TRADINGAGENTS_DEEP_THINK_LLM"] = alert.deep_think_llm
    if alert.quick_think_llm is not None:
        env["TRADINGAGENTS_QUICK_THINK_LLM"] = alert.quick_think_llm
    if alert.anthropic_effort is not None:
        env["TRADINGAGENTS_ANTHROPIC_EFFORT"] = alert.anthropic_effort
    if alert.max_debate_rounds is not None:
        env["TRADINGAGENTS_MAX_DEBATE_ROUNDS"] = str(alert.max_debate_rounds)
    if alert.max_risk_discuss_rounds is not None:
        env["TRADINGAGENTS_MAX_RISK_ROUNDS"] = str(alert.max_risk_discuss_rounds)
    return env


async def _set_status(result_id: int, **fields) -> None:
    async with AsyncSessionLocal() as session:
        analysis = await session.get(AnalysisResult, result_id)
        if analysis is None:
            _log.warning("run_analysis: AnalysisResult %d not found", result_id)
            return
        for key, value in fields.items():
            setattr(analysis, key, value)
        await session.commit()


def _parse_heartbeat(line: bytes) -> dict[str, int] | None:
    """Parses a HEARTBEAT stderr line into its counter fields.

    Matches on substring, not prefix — the child logs via ``logging.info``,
    which prepends "INFO:__main__:" (default format, left untouched so other
    log lines in the child aren't affected).
    """
    text = line.decode(errors="replace")
    if "HEARTBEAT" not in text:
        return None
    fields: dict[str, int] = {}
    for token in text.split():
        key, sep, value = token.partition("=")
        if sep and key in _HEARTBEAT_FIELDS:
            try:
                fields[key] = int(value)
            except ValueError:
                _log.warning("run_analysis: malformed heartbeat field %r in line %r", token, text)
                continue
    return fields or None


async def _drain_stdout(process: asyncio.subprocess.Process) -> bytes:
    assert process.stdout is not None
    return await process.stdout.read()


async def _watch_stderr(
    process: asyncio.subprocess.Process, result_id: int, idle_timeout: float
) -> tuple[str | None, str]:
    """Reads stderr line-by-line, updating AnalysisResult progress on each
    HEARTBEAT line and resetting an idle timer on every line received.

    Deliberately resets on *any* stderr line, not just HEARTBEAT ones — any
    output at all proves the child is alive, and being stricter (heartbeat-only)
    would only make this fire more eagerly for no real benefit.

    Returns (kill_reason, full_stderr_text) — kill_reason is "idle_timeout"
    if killed for inactivity, or None on clean EOF (process exited on its own,
    successfully or not — the caller checks the returncode separately).
    """
    assert process.stderr is not None
    lines: list[bytes] = []
    while True:
        try:
            line = await asyncio.wait_for(process.stderr.readline(), timeout=idle_timeout)
        except asyncio.TimeoutError:
            process.kill()
            return "idle_timeout", b"".join(lines).decode(errors="replace")

        if not line:
            return None, b"".join(lines).decode(errors="replace")

        lines.append(line)
        heartbeat = _parse_heartbeat(line)
        if heartbeat is not None:
            await _set_status(
                result_id,
                last_heartbeat_at=datetime.now(timezone.utc),
                **heartbeat,
            )


async def run_analysis(alert: StockAlert, result_id: int) -> None:
    """Fire-and-forget entry point — must never let an exception escape.

    This runs inside a detached asyncio.Task (see spawn()); an unhandled
    exception here doesn't crash anything visibly, it just becomes an
    "exception was never retrieved" warning while the AnalysisResult row is
    stuck at status="running" forever — and since analysis_results has a
    partial unique index on (ticker) WHERE status IN ('pending','running'),
    a stuck row blocks every future analysis attempt for that ticker until
    someone fixes it by hand. The targeted except blocks below cover known
    failure modes; this catch-all is the backstop for everything else
    (e.g. FileNotFoundError if the venv path is wrong, a DB hiccup).
    """
    try:
        await _run_analysis(alert, result_id)
    except Exception:
        _log.error(
            "run_analysis: unexpected failure for %s", alert.ticker, exc_info=True
        )
        await _set_status(result_id, status="failed")


async def _run_analysis(alert: StockAlert, result_id: int) -> None:
    await _set_status(result_id, status="running")

    if not os.path.isdir(settings.tradingagents_path):
        _log.error(
            "run_analysis: TradingAgents path %s missing — cannot run analysis for %s",
            settings.tradingagents_path,
            alert.ticker,
        )
        await _set_status(result_id, status="failed")
        return

    analysts_csv = alert.analysts or "market,social,news,fundamentals"
    # UTC "today" — a deliberate simplification, not per-market trading-day-aware.
    # Can be off by one for non-US tickers right around the UTC day boundary.
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    env = _build_env(alert)

    process = await asyncio.create_subprocess_exec(
        settings.tradingagents_venv_python,
        _WRAPPER_SCRIPT,
        alert.ticker,
        trade_date,
        "--analysts",
        analysts_csv,
        env=env,
        cwd=settings.tradingagents_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_task = asyncio.create_task(_drain_stdout(process))
    stderr_task = asyncio.create_task(
        _watch_stderr(process, result_id, settings.tradingagents_idle_timeout_seconds)
    )

    try:
        kill_reason, stderr_text = await asyncio.wait_for(
            stderr_task, timeout=settings.tradingagents_hard_cap_seconds
        )
    except asyncio.TimeoutError:
        process.kill()
        kill_reason, stderr_text = "max_runtime_exceeded", ""

    stdout = await stdout_task
    await process.wait()

    if kill_reason is not None:
        _log.error(
            "run_analysis: TradingAgents run for %s killed (%s): %s",
            alert.ticker,
            kill_reason,
            stderr_text,
        )
        await _set_status(result_id, status="failed", error_reason=kill_reason)
        return

    if process.returncode != 0:
        _log.error(
            "run_analysis: TradingAgents run for %s exited %d: %s",
            alert.ticker,
            process.returncode,
            stderr_text,
        )
        await _set_status(result_id, status="failed", error_reason="subprocess_error")
        return

    try:
        parsed = json.loads(stdout.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        _log.error(
            "run_analysis: could not parse TradingAgents stdout for %s: %r",
            alert.ticker,
            stdout[:500],
        )
        await _set_status(result_id, status="failed", error_reason="invalid_output")
        return

    await _set_status(
        result_id,
        status="done",
        result=parsed,
        action=parsed.get("decision"),
        price_target=parsed.get("price_target"),
        report_path=parsed.get("report_path"),
        completed_at=datetime.now(timezone.utc),
    )

    decision = parsed.get("decision", "?")
    summary = (parsed.get("executive_summary") or parsed.get("final_trade_decision") or "")[:500]
    await send_alert(title=f"TradingAgents: {alert.ticker} → {decision}", body=summary)
