from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import analysis


def _fake_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    process = MagicMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


@pytest.mark.asyncio
async def test_communicate_with_timeout_kills_process_on_hang():
    process = _fake_process()
    process.communicate = AsyncMock(side_effect=TimeoutError)

    returncode, output = await analysis._communicate_with_timeout(process, 1, "git fetch")

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    assert returncode == 1
    assert "timed out after 1s" in output


@pytest.mark.asyncio
async def test_version_not_cloned_returns_available_false():
    with patch("app.api.analysis.os.path.isdir", return_value=False):
        result = await analysis.get_tradingagents_version()

    assert result == {"available": False}


@pytest.mark.asyncio
async def test_version_fetch_failure_returns_available_false_with_error():
    fetch_process = _fake_process(stderr=b"network unreachable", returncode=1)

    with (
        patch("app.api.analysis.os.path.isdir", return_value=True),
        patch(
            "app.api.analysis.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=fetch_process),
        ),
    ):
        result = await analysis.get_tradingagents_version()

    assert result["available"] is False
    assert "network unreachable" in result["error"]


@pytest.mark.asyncio
async def test_version_success_reports_behind_count():
    responses = [
        _fake_process(returncode=0),  # git fetch
        _fake_process(stdout=b"abc1234\n"),  # rev-parse HEAD
        _fake_process(stdout=b"def5678\n"),  # rev-parse origin/main
        _fake_process(stdout=b"2026-06-15T10:00:00+00:00\n"),  # log HEAD
        _fake_process(stdout=b"2026-06-28T14:00:00+00:00\n"),  # log origin/main
        _fake_process(stdout=b"3\n"),  # rev-list --count
    ]

    with (
        patch("app.api.analysis.os.path.isdir", return_value=True),
        patch(
            "app.api.analysis.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=responses),
        ),
    ):
        result = await analysis.get_tradingagents_version()

    assert result["current_commit"] == "abc1234"
    assert result["latest_commit"] == "def5678"
    assert result["behind_count"] == 3
    assert result["update_available"] is True


@pytest.mark.asyncio
async def test_version_up_to_date_reports_update_not_available():
    responses = [
        _fake_process(returncode=0),  # git fetch
        _fake_process(stdout=b"abc1234\n"),
        _fake_process(stdout=b"abc1234\n"),
        _fake_process(stdout=b"2026-06-15T10:00:00+00:00\n"),
        _fake_process(stdout=b"2026-06-15T10:00:00+00:00\n"),
        _fake_process(stdout=b"0\n"),
    ]

    with (
        patch("app.api.analysis.os.path.isdir", return_value=True),
        patch(
            "app.api.analysis.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=responses),
        ),
    ):
        result = await analysis.get_tradingagents_version()

    assert result["behind_count"] == 0
    assert result["update_available"] is False


@pytest.mark.asyncio
async def test_update_pull_failure_returns_success_false():
    pull_process = _fake_process(stderr=b"merge conflict", returncode=1)

    with patch(
        "app.api.analysis.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=pull_process),
    ):
        result = await analysis.update_tradingagents()

    assert result["success"] is False
    assert result["new_commit"] is None
    assert "merge conflict" in result["output"]


@pytest.mark.asyncio
async def test_update_pip_install_failure_returns_success_false():
    pull_process = _fake_process(stdout=b"Already up to date.", returncode=0)
    pip_process = _fake_process(stderr=b"could not find a version", returncode=1)

    with patch(
        "app.api.analysis.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=[pull_process, pip_process]),
    ):
        result = await analysis.update_tradingagents()

    assert result["success"] is False
    assert result["new_commit"] is None
    assert "could not find a version" in result["output"]


@pytest.mark.asyncio
async def test_update_success_returns_new_commit():
    pull_process = _fake_process(stdout=b"Updating abc123..def456", returncode=0)
    pip_process = _fake_process(stdout=b"Successfully installed foo-1.0", returncode=0)
    rev_parse_process = _fake_process(stdout=b"def456\n")

    with patch(
        "app.api.analysis.asyncio.create_subprocess_exec",
        new=AsyncMock(side_effect=[pull_process, pip_process, rev_parse_process]),
    ):
        result = await analysis.update_tradingagents()

    assert result["success"] is True
    assert result["new_commit"] == "def456"
    assert "Updating abc123..def456" in result["output"]
    assert "Successfully installed foo-1.0" in result["output"]
