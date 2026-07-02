import asyncio
import json
import logging
import os
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.models.analysis_result import AnalysisResult
from app.models.stock_alert import StockAlert
from app.services.notifications import send_alert

_log = logging.getLogger(__name__)

_WRAPPER_SCRIPT = str(Path(__file__).resolve().parents[2] / "scripts" / "run_tradingagents.py")
_TIMEOUT_SECONDS = 30 * 60

_background_tasks: set[asyncio.Task[None]] = set()


def spawn(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    """Fire-and-forget a coroutine while keeping a strong reference to its Task.

    asyncio.create_task()'s result must be held somewhere or it can be
    garbage-collected mid-run — this registry is that somewhere.
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        _log.error(
            "run_analysis: TradingAgents run for %s timed out after %ds",
            alert.ticker,
            _TIMEOUT_SECONDS,
        )
        await _set_status(result_id, status="failed")
        return

    if process.returncode != 0:
        _log.error(
            "run_analysis: TradingAgents run for %s exited %d: %s",
            alert.ticker,
            process.returncode,
            stderr.decode(errors="replace"),
        )
        await _set_status(result_id, status="failed")
        return

    try:
        parsed = json.loads(stdout.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        _log.error(
            "run_analysis: could not parse TradingAgents stdout for %s: %r",
            alert.ticker,
            stdout[:500],
        )
        await _set_status(result_id, status="failed")
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
