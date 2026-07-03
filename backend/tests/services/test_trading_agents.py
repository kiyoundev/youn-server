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


def _fake_process(
    *,
    stderr_lines: list[bytes | BaseException],
    stdout: bytes = b"",
    returncode: int = 0,
) -> MagicMock:
    """Fake asyncio subprocess.Process — stdout/stderr mocked as separate
    streams (not communicate()), matching the concurrent stdout-drain /
    stderr-watch read loop _run_analysis now uses.

    stderr_lines is consumed one call at a time by stderr.readline(); an
    entry that's an exception instance (e.g. asyncio.TimeoutError()) makes
    that call raise instead of return — used to simulate an idle timeout
    without any real waiting, since _watch_stderr's except block reacts to
    TimeoutError regardless of whether it came from a real timer or not.
    """
    process = MagicMock()
    process.returncode = returncode
    process.stdout = MagicMock()
    process.stdout.read = AsyncMock(return_value=stdout)
    process.stderr = MagicMock()
    process.stderr.readline = AsyncMock(side_effect=stderr_lines)
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


# --- _parse_heartbeat --------------------------------------------------------


def test_parse_heartbeat_extracts_known_fields_from_logging_formatted_line():
    line = b"INFO:__main__:HEARTBEAT llm_calls=3 tokens_in=1200 tokens_out=340 tool_calls=1\n"
    assert trading_agents._parse_heartbeat(line) == {
        "llm_calls": 3,
        "tokens_in": 1200,
        "tokens_out": 340,
        "tool_calls": 1,
    }


def test_parse_heartbeat_returns_none_for_non_heartbeat_line():
    assert trading_agents._parse_heartbeat(b"INFO:__main__:starting up\n") is None


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
    process = _fake_process(stderr_lines=[b""], stdout=json.dumps(payload).encode())

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
    process.kill.assert_not_called()
    send_alert.assert_awaited_once()
    _, kwargs = send_alert.call_args
    assert "AAPL" in kwargs["title"]
    assert "Buy" in kwargs["title"]
    assert kwargs["body"] == "Enter now."


@pytest.mark.asyncio
async def test_run_analysis_heartbeat_updates_progress_fields():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    payload = {"decision": "Hold"}
    process = _fake_process(
        stderr_lines=[
            b"INFO:__main__:HEARTBEAT llm_calls=1 tokens_in=100 tokens_out=20 tool_calls=0\n",
            b"",
        ],
        stdout=json.dumps(payload).encode(),
    )

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch("app.services.trading_agents.send_alert", new=AsyncMock()),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    assert analysis.llm_calls == 1
    assert analysis.tokens_in == 100
    assert analysis.tokens_out == 20
    assert analysis.tool_calls == 0
    assert analysis.last_heartbeat_at is not None
    assert analysis.status == "done"


@pytest.mark.asyncio
async def test_run_analysis_continuous_heartbeats_completes():
    """Regression guard for the exact bug #17 fixes: a run producing steady
    heartbeats for longer than the old flat 30-minute timeout must still
    complete, not get killed just for taking a while."""
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    payload = {"decision": "Sell"}
    heartbeat_line = b"INFO:__main__:HEARTBEAT llm_calls=1 tokens_in=10 tokens_out=5 tool_calls=0\n"
    process = _fake_process(
        stderr_lines=[heartbeat_line] * 40 + [b""],
        stdout=json.dumps(payload).encode(),
    )

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch("app.services.trading_agents.send_alert", new=AsyncMock()),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    process.kill.assert_not_called()
    assert analysis.status == "done"


@pytest.mark.asyncio
async def test_run_analysis_idle_timeout_kills_process_and_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    process = _fake_process(stderr_lines=[asyncio.TimeoutError()])

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
    assert analysis.error_reason == "idle_timeout"


@pytest.mark.asyncio
async def test_run_analysis_hard_cap_exceeded_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)

    async def _never_ending_heartbeats(*args, **kwargs):
        await asyncio.sleep(0.01)
        return b"INFO:__main__:HEARTBEAT llm_calls=1 tokens_in=0 tokens_out=0 tool_calls=0\n"

    process = _fake_process(stderr_lines=[])
    process.stderr.readline = AsyncMock(side_effect=_never_ending_heartbeats)

    with (
        patch("app.services.trading_agents.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.trading_agents.os.path.isdir", return_value=True),
        patch(
            "app.services.trading_agents.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch.object(trading_agents.settings, "tradingagents_hard_cap_seconds", 0.05),
    ):
        await trading_agents.run_analysis(_alert(), 1)

    process.kill.assert_called_once()
    assert analysis.status == "failed"
    assert analysis.error_reason == "max_runtime_exceeded"


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
    process = _fake_process(stderr_lines=[b"traceback here\n", b""], returncode=1)

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
    assert analysis.error_reason == "subprocess_error"


@pytest.mark.asyncio
async def test_run_analysis_bad_json_sets_failed():
    analysis = SimpleNamespace(status="pending")
    session = _session_for(analysis)
    process = _fake_process(stderr_lines=[b""], stdout=b"not json, some stray log line")

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
    assert analysis.error_reason == "invalid_output"


# --- spawn --------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_holds_and_releases_task_reference():
    async def _noop():
        return None

    task = trading_agents.spawn(_noop())
    assert task in trading_agents._background_tasks

    await task
    assert task not in trading_agents._background_tasks
