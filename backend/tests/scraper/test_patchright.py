"""Tests for PatchrightScraper class-level state behaviour."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.scraper.patchright_scraper import PatchrightScraper
from app.services.scraper.result import ScraperResult


@pytest.fixture(autouse=True)
def reset_patchright_state():
    """Isolate each test from class-level browser state.

    Also gives each test a fresh _start_lock. Not strictly required in
    Python 3.10+ (asyncio.Lock no longer binds to a specific event loop, so
    reusing one instance across tests' separate per-function loops is safe
    in practice) — but cheap insurance against relying on that specifically,
    and keeps every piece of PatchrightScraper's class state equally isolated
    rather than isolating some pieces and not others.
    """
    original_context = PatchrightScraper._context
    original_playwright = PatchrightScraper._playwright
    original_active_scrapes = PatchrightScraper._active_scrapes
    original_start_lock = PatchrightScraper._start_lock
    original_xvfb_process = PatchrightScraper._xvfb_process
    PatchrightScraper._context = None
    PatchrightScraper._playwright = None
    PatchrightScraper._active_scrapes = 0
    PatchrightScraper._start_lock = asyncio.Lock()
    PatchrightScraper._xvfb_process = None
    yield
    PatchrightScraper._context = original_context
    PatchrightScraper._start_lock = original_start_lock
    PatchrightScraper._playwright = original_playwright
    PatchrightScraper._active_scrapes = original_active_scrapes
    PatchrightScraper._xvfb_process = original_xvfb_process


@pytest.fixture
def stub_xvfb_already_running():
    """Opt-in (not autouse) — the lock-file tests near the bottom of this
    file exercise the real _xvfb_already_running() implementation directly
    and must NOT have it stubbed. Tests that only care about start_browser()'s
    spawn-decision branching request this explicitly instead."""
    with patch.object(PatchrightScraper, "_xvfb_already_running", return_value=False) as mock:
        yield mock


@pytest.mark.asyncio
async def test_get_price_launches_lazily_when_context_missing() -> None:
    """get_price() calls start_browser() rather than short-circuiting — no
    real browser/network involved, everything mocked at the boundary."""
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_page.wait_for_function = AsyncMock(side_effect=Exception("no cloudflare challenge"))
    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    async def fake_start_browser() -> None:
        PatchrightScraper._context = mock_context

    with patch.object(PatchrightScraper, "start_browser", AsyncMock(side_effect=fake_start_browser)) as mock_start:
        result = await PatchrightScraper().get_price("https://example.com/product")

    mock_start.assert_awaited_once()
    mock_page.goto.assert_awaited_once()
    mock_page.close.assert_awaited_once()
    assert result == ScraperResult(price=None, status="error")  # no price signals in "<html></html>"


@pytest.mark.asyncio
async def test_get_price_returns_error_when_launch_fails() -> None:
    """If start_browser() itself raises (e.g. Chromium unreachable), get_price()
    degrades to status="error" rather than letting the exception propagate."""
    with patch.object(PatchrightScraper, "start_browser", AsyncMock(side_effect=RuntimeError("boom"))):
        result = await PatchrightScraper().get_price("https://example.com/product")
    assert result == ScraperResult(price=None, status="error")


@pytest.mark.asyncio
async def test_start_browser_idempotent() -> None:
    sentinel = object()
    PatchrightScraper._context = sentinel  # type: ignore[assignment]
    await PatchrightScraper.start_browser()
    assert PatchrightScraper._context is sentinel


@pytest.mark.asyncio
async def test_start_browser_concurrent_callers_launch_once() -> None:
    """Multiple concurrent start_browser() calls, none of them seeing _context
    set yet, must still result in exactly one real launch — the property
    the lock exists for."""
    import asyncio

    launch_count = 0

    async def fake_launch_persistent_context(*args, **kwargs):
        nonlocal launch_count
        launch_count += 1
        await asyncio.sleep(0.01)  # simulate a slow launch, widening the race window
        return MagicMock()

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch_persistent_context = AsyncMock(side_effect=fake_launch_persistent_context)
    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.start = AsyncMock(return_value=mock_playwright_instance)

    with (
        patch(
            "app.services.scraper.patchright_scraper.async_playwright",
            return_value=mock_playwright_cm,
        ),
        patch(
            "app.services.scraper.patchright_scraper.asyncio.create_subprocess_exec",
            AsyncMock(return_value=MagicMock()),
        ),
        patch.object(PatchrightScraper, "_xvfb_already_running", return_value=False),
    ):
        await asyncio.gather(*(PatchrightScraper.start_browser() for _ in range(5)))

    assert launch_count == 1
    assert PatchrightScraper._context is not None


@pytest.mark.asyncio
async def test_start_browser_cleans_up_playwright_on_launch_failure() -> None:
    """A failed launch_persistent_context() must stop the already-started
    Playwright driver, not leave it orphaned for the next attempt to
    silently overwrite (see .plan/40-.../review.md Major #3)."""
    mock_playwright_instance = MagicMock()
    mock_playwright_instance.stop = AsyncMock()
    mock_playwright_instance.chromium.launch_persistent_context = AsyncMock(side_effect=RuntimeError("launch failed"))
    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.start = AsyncMock(return_value=mock_playwright_instance)

    with (
        patch(
            "app.services.scraper.patchright_scraper.async_playwright",
            return_value=mock_playwright_cm,
        ),
        patch(
            "app.services.scraper.patchright_scraper.asyncio.create_subprocess_exec",
            AsyncMock(return_value=MagicMock()),
        ),
        patch.object(PatchrightScraper, "_xvfb_already_running", return_value=False),
    ):
        with pytest.raises(RuntimeError):
            await PatchrightScraper.start_browser()

    mock_playwright_instance.stop.assert_awaited_once()
    assert PatchrightScraper._playwright is None
    assert PatchrightScraper._context is None


@pytest.mark.asyncio
async def test_close_if_idle_closes_when_no_active_scrapes() -> None:
    PatchrightScraper._context = object()  # type: ignore[assignment]
    PatchrightScraper._active_scrapes = 0
    with patch.object(PatchrightScraper, "close_browser", AsyncMock()) as mock_close:
        await PatchrightScraper.close_if_idle()
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_if_idle_skips_when_scrape_in_flight() -> None:
    sentinel = object()
    PatchrightScraper._context = sentinel  # type: ignore[assignment]
    PatchrightScraper._active_scrapes = 1
    with patch.object(PatchrightScraper, "close_browser", AsyncMock()) as mock_close:
        await PatchrightScraper.close_if_idle()
    mock_close.assert_not_awaited()
    assert PatchrightScraper._context is sentinel


@pytest.mark.asyncio
async def test_close_if_idle_serializes_concurrent_callers_against_double_close() -> None:
    """Two independent callers (e.g. poll_prices and a #41 ad-hoc batch)
    finishing at nearly the same moment must not both call close_browser()
    on the same context — close_browser()'s own await on _context.close()
    leaves _context non-None until it returns, so without _start_lock
    serializing the check-and-close sequence, a second concurrent caller
    could see the same still-truthy _context and close it a second time."""
    PatchrightScraper._context = object()  # type: ignore[assignment]
    PatchrightScraper._active_scrapes = 0

    async def fake_close_browser() -> None:
        await asyncio.sleep(0.01)  # widen the race window, as in test_start_browser_concurrent_callers_launch_once
        PatchrightScraper._context = None

    with patch.object(PatchrightScraper, "close_browser", AsyncMock(side_effect=fake_close_browser)) as mock_close:
        await asyncio.gather(*(PatchrightScraper.close_if_idle() for _ in range(5)))

    mock_close.assert_awaited_once()


async def _start_browser_with_playwright_mocked() -> None:
    """Shared helper for the Xvfb tests below — drives start_browser() to
    the point of spawning/skipping Xvfb without a real Chromium launch."""
    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch_persistent_context = AsyncMock(return_value=MagicMock())
    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.start = AsyncMock(return_value=mock_playwright_instance)
    with patch(
        "app.services.scraper.patchright_scraper.async_playwright",
        return_value=mock_playwright_cm,
    ):
        await PatchrightScraper.start_browser()


@pytest.mark.asyncio
async def test_start_browser_spawns_xvfb_when_not_running(stub_xvfb_already_running: MagicMock) -> None:
    stub_xvfb_already_running.return_value = False
    with patch(
        "app.services.scraper.patchright_scraper.asyncio.create_subprocess_exec",
        AsyncMock(return_value=MagicMock()),
    ) as mock_spawn:
        await _start_browser_with_playwright_mocked()
    mock_spawn.assert_awaited_once()
    assert mock_spawn.call_args.args[0] == "Xvfb"
    assert os.environ["DISPLAY"] == ":99"


@pytest.mark.asyncio
async def test_start_browser_skips_xvfb_spawn_when_already_alive(stub_xvfb_already_running: MagicMock) -> None:
    """_xvfb_process.returncode is None (still running, tracked in-process)
    — no new spawn, no lock-file check needed either."""
    mock_xvfb = MagicMock()
    mock_xvfb.returncode = None
    PatchrightScraper._xvfb_process = mock_xvfb
    with patch(
        "app.services.scraper.patchright_scraper.asyncio.create_subprocess_exec",
        AsyncMock(),
    ) as mock_spawn:
        await _start_browser_with_playwright_mocked()
    mock_spawn.assert_not_awaited()
    stub_xvfb_already_running.assert_not_called()


@pytest.mark.asyncio
async def test_start_browser_respawns_xvfb_when_previous_died(stub_xvfb_already_running: MagicMock) -> None:
    """_xvfb_process.returncode is not None (process has exited) — treated
    the same as never having started one."""
    dead_xvfb = MagicMock()
    dead_xvfb.returncode = 1  # exited
    PatchrightScraper._xvfb_process = dead_xvfb
    stub_xvfb_already_running.return_value = False
    with patch(
        "app.services.scraper.patchright_scraper.asyncio.create_subprocess_exec",
        AsyncMock(return_value=MagicMock()),
    ) as mock_spawn:
        await _start_browser_with_playwright_mocked()
    mock_spawn.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_browser_reuses_externally_alive_xvfb(stub_xvfb_already_running: MagicMock) -> None:
    """_xvfb_process is None (not tracked in this process), but
    _xvfb_already_running() finds a real live one via the lock file (e.g. an
    orphan from an earlier standalone script run against the same
    container) — reuse it, don't spawn a second one."""
    stub_xvfb_already_running.return_value = True
    with patch(
        "app.services.scraper.patchright_scraper.asyncio.create_subprocess_exec",
        AsyncMock(),
    ) as mock_spawn:
        await _start_browser_with_playwright_mocked()
    mock_spawn.assert_not_awaited()
    assert os.environ["DISPLAY"] == ":99"


@pytest.mark.asyncio
async def test_xvfb_already_running_true_for_live_pid_with_matching_comm(tmp_path) -> None:
    lock_file = tmp_path / ".X99-lock"
    lock_file.write_text(str(os.getpid()))  # our own PID — definitely alive
    with (
        patch("app.services.scraper.patchright_scraper._XVFB_LOCK_FILE", str(lock_file)),
        patch("app.services.scraper.patchright_scraper._read_proc_comm", return_value="Xvfb"),
    ):
        assert PatchrightScraper._xvfb_already_running() is True
    assert lock_file.exists()  # untouched — a live, identity-confirmed process's lock isn't removed


@pytest.mark.asyncio
async def test_xvfb_already_running_false_when_pid_reassigned_to_different_process(tmp_path) -> None:
    """The PID is genuinely alive, but it's not Xvfb anymore — e.g. Xvfb was
    hard-killed without cleaning up its lock, and the OS later reassigned
    that same PID to an unrelated process over this app's long uptime.
    Trusting existence alone would wrongly report "running"."""
    lock_file = tmp_path / ".X99-lock"
    lock_file.write_text(str(os.getpid()))  # alive, but not really Xvfb
    with (
        patch("app.services.scraper.patchright_scraper._XVFB_LOCK_FILE", str(lock_file)),
        patch("app.services.scraper.patchright_scraper._read_proc_comm", return_value="some-other-proc"),
    ):
        assert PatchrightScraper._xvfb_already_running() is False
    assert not lock_file.exists()  # identity mismatch treated the same as a stale lock


@pytest.mark.asyncio
async def test_xvfb_already_running_cleans_up_stale_lock(tmp_path) -> None:
    lock_file = tmp_path / ".X99-lock"
    # A PID essentially guaranteed not to exist on any real system.
    lock_file.write_text("999999")
    with patch("app.services.scraper.patchright_scraper._XVFB_LOCK_FILE", str(lock_file)):
        assert PatchrightScraper._xvfb_already_running() is False
    assert not lock_file.exists()  # stale lock cleaned up


@pytest.mark.asyncio
async def test_xvfb_already_running_false_when_no_lock_file(tmp_path) -> None:
    missing = tmp_path / ".X99-lock"  # never created
    with patch("app.services.scraper.patchright_scraper._XVFB_LOCK_FILE", str(missing)):
        assert PatchrightScraper._xvfb_already_running() is False


@pytest.mark.asyncio
async def test_xvfb_already_running_false_for_non_positive_pid(tmp_path) -> None:
    """A malformed lock (e.g. "0") must not be trusted — os.kill(0, 0)
    signals our own process group, not a specific PID, and would otherwise
    spuriously report "alive"."""
    lock_file = tmp_path / ".X99-lock"
    lock_file.write_text("0")
    with patch("app.services.scraper.patchright_scraper._XVFB_LOCK_FILE", str(lock_file)):
        assert PatchrightScraper._xvfb_already_running() is False


@pytest.mark.asyncio
async def test_stop_xvfb_terminates_and_clears() -> None:
    mock_xvfb = MagicMock()
    mock_xvfb.wait = AsyncMock()
    PatchrightScraper._xvfb_process = mock_xvfb
    await PatchrightScraper.stop_xvfb()
    mock_xvfb.terminate.assert_called_once()
    mock_xvfb.wait.assert_awaited_once()
    assert PatchrightScraper._xvfb_process is None


@pytest.mark.asyncio
async def test_stop_xvfb_noop_when_never_started() -> None:
    PatchrightScraper._xvfb_process = None
    await PatchrightScraper.stop_xvfb()  # must not raise
    assert PatchrightScraper._xvfb_process is None


@pytest.mark.asyncio
async def test_close_browser_does_not_touch_xvfb_process() -> None:
    """Core design property (#15): close_browser() must never restart/kill
    Xvfb — only start_browser() and stop_xvfb() may touch _xvfb_process."""
    mock_xvfb = MagicMock()
    PatchrightScraper._xvfb_process = mock_xvfb
    PatchrightScraper._context = MagicMock(close=AsyncMock())
    await PatchrightScraper.close_browser()
    mock_xvfb.terminate.assert_not_called()
    assert PatchrightScraper._xvfb_process is mock_xvfb


@pytest.mark.asyncio
async def test_close_if_idle_does_not_touch_xvfb_process() -> None:
    mock_xvfb = MagicMock()
    PatchrightScraper._xvfb_process = mock_xvfb
    PatchrightScraper._context = object()  # type: ignore[assignment]
    PatchrightScraper._active_scrapes = 0
    with patch.object(PatchrightScraper, "close_browser", AsyncMock()):
        await PatchrightScraper.close_if_idle()
    mock_xvfb.terminate.assert_not_called()
    assert PatchrightScraper._xvfb_process is mock_xvfb
