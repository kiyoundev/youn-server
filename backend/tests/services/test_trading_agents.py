import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import trading_agents


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _alert(
    *,
    ticker: str = "AAPL",
    deep_think_llm: str | None = None,
    quick_think_llm: str | None = None,
    anthropic_effort: str | None = None,
    max_debate_rounds: int | None = None,
    max_risk_discuss_rounds: int | None = None,
    analysts: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        ticker=ticker,
        deep_think_llm=deep_think_llm,
        quick_think_llm=quick_think_llm,
        anthropic_effort=anthropic_effort,
        max_debate_rounds=max_debate_rounds,
        max_risk_discuss_rounds=max_risk_discuss_rounds,
        analysts=analysts,
    )


def _session_for(analysis: SimpleNamespace) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=analysis)
    session.commit = AsyncMock()
    return session


def _fake_process(stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    process = MagicMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


# --- _build_env --------------------------------------------------------


def test_build_env_omits_null_fields():
    alert = _alert()
    env = trading_agents._build_env(alert)

    assert "TRADINGAGENTS_DEEP_THINK_LLM" not in env
    assert "TRADINGAGENTS_QUICK_THINK_LLM" not in env
    assert "TRADINGAGENTS_ANTHROPIC_EFFORT" not in env
    assert "TRADINGAGENTS_MAX_DEBATE_ROUNDS" not in env
    assert "TRADINGAGENTS_MAX_RISK_ROUNDS" not in env


def test_build_env_sets_only_non_null_fields():
    alert = _alert(anthropic_effort="high", max_debate_rounds=5)
    env = trading_agents._build_env(alert)

    assert env["TRADINGAGENTS_ANTHROPIC_EFFORT"] == "high"
    assert env["TRADINGAGENTS_MAX_DEBATE_ROUNDS"] == "5"
    assert "TRADINGAGENTS_DEEP_THINK_LLM" not in env
    assert "TRADINGAGENTS_MAX_RISK_ROUNDS" not in env


def test_build_env_always_sets_pythonpath_and_results_dir():
    env = trading_agents._build_env(_alert())
    assert env["PYTHONPATH"] == trading_agents.settings.tradingagents_path
    assert env["TRADINGAGENTS_RESULTS_DIR"] == trading_agents.settings.tradingagents_results_dir


# --- run_analysis --------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analysis_missing_path_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=False),
        patch("app.services.trading_agents.asyncio.create_subprocess_exec") as spawn_exec,
    ):
        await trading_agents.run_analysis(_alert(), 1)

    spawn_exec.assert_not_called()
    assert analysis.status == "failed"


@pytest.mark.asyncio
async def test_run_analysis_success_updates_all_fields_and_sends_push():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    payload = {
        "decision": "Buy",
        "price_target": 123.45,
        "executive_summary": "Enter now.",
        "final_trade_decision": "**Rating**: Buy",
        "report_path": "/opt/tradingagents/data/reports/AAPL_20260701",
    }
    process = _fake_process(json.dumps(payload).encode())

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch("app.services.trading_agents.send_alert", new=AsyncMock()) as send_alert,
    ):
        await trading_agents.run_analysis(_alert(), 1)

    assert analysis.status == "done"
    assert analysis.result == payload
    assert analysis.action == "Buy"
    assert analysis.price_target == 123.45
    assert analysis.report_path == "/opt/tradingagents/data/reports/AAPL_20260701"
    assert analysis.completed_at is not None
    send_alert.assert_awaited_once()
    _, kwargs = send_alert.call_args
    assert "AAPL" in kwargs["title"]
    assert "Buy" in kwargs["title"]
    assert kwargs["body"] == "Enter now."


@pytest.mark.asyncio
async def test_run_analysis_timeout_kills_process_and_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    process = _fake_process(b"")
    process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    assert analysis.status == "failed"


@pytest.mark.asyncio
async def test_run_analysis_unexpected_exception_sets_failed_not_stuck_running():
    """Catch-all backstop: e.g. the venv path is wrong and exec itself raises,
    not one of the specific handled failure modes (timeout/non-zero exit/bad JSON).
    Must still end at status="failed", not leave the row stuck at "running"."""
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=FileNotFoundError("no such file: venv python")),
        ),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    assert analysis.status == "failed"


@pytest.mark.asyncio
async def test_run_analysis_nonzero_exit_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    process = _fake_process(b"", b"traceback here", returncode=1)

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    assert analysis.status == "failed"


@pytest.mark.asyncio
async def test_run_analysis_bad_json_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    process = _fake_process(b"not json, some stray log line")

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    assert analysis.status == "failed"


# --- spawn --------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_holds_and_releases_task_reference():
    async def _noop():
        return None

    task = trading_agents.spawn(_noop())
    assert task in trading_agents._background_tasks

    await task
    assert task not in trading_agents._background_tasks
