"""Tests for PatchrightScraper class-level state behaviour."""

import asyncio
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
    PatchrightScraper._context = None
    PatchrightScraper._playwright = None
    PatchrightScraper._active_scrapes = 0
    PatchrightScraper._start_lock = asyncio.Lock()
    yield
    PatchrightScraper._context = original_context
    PatchrightScraper._start_lock = original_start_lock
    PatchrightScraper._playwright = original_playwright
    PatchrightScraper._active_scrapes = original_active_scrapes


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

    with patch.object(
        PatchrightScraper, "start_browser", AsyncMock(side_effect=fake_start_browser)
    ) as mock_start:
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
    mock_playwright_instance.chromium.launch_persistent_context = AsyncMock(
        side_effect=fake_launch_persistent_context
    )
    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.start = AsyncMock(return_value=mock_playwright_instance)

    with patch(
        "app.services.scraper.patchright_scraper.async_playwright",
        return_value=mock_playwright_cm,
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
    mock_playwright_instance.chromium.launch_persistent_context = AsyncMock(
        side_effect=RuntimeError("launch failed")
    )
    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.start = AsyncMock(return_value=mock_playwright_instance)

    with patch(
        "app.services.scraper.patchright_scraper.async_playwright",
        return_value=mock_playwright_cm,
    ):
        with pytest.raises(RuntimeError):
            await PatchrightScraper.start_browser()

    mock_playwright_instance.stop.assert_awaited_once()
    assert PatchrightScraper._playwright is None
    assert PatchrightScraper._context is None


@pytest.mark.asyncio
async def test_recycle_browser_noop_when_never_launched() -> None:
    await PatchrightScraper.recycle_browser()
    assert PatchrightScraper._context is None


@pytest.mark.asyncio
async def test_recycle_browser_skips_when_scrape_in_flight() -> None:
    sentinel = object()
    PatchrightScraper._context = sentinel  # type: ignore[assignment]
    PatchrightScraper._active_scrapes = 1
    with patch.object(PatchrightScraper, "close_browser", AsyncMock()) as mock_close:
        await PatchrightScraper.recycle_browser()
    mock_close.assert_not_awaited()
    assert PatchrightScraper._context is sentinel


@pytest.mark.asyncio
async def test_recycle_browser_closes_and_relaunches_when_idle() -> None:
    PatchrightScraper._context = object()  # type: ignore[assignment]
    PatchrightScraper._active_scrapes = 0
    new_context = object()

    async def fake_close() -> None:
        PatchrightScraper._context = None

    async def fake_start() -> None:
        PatchrightScraper._context = new_context

    with (
        patch.object(PatchrightScraper, "close_browser", AsyncMock(side_effect=fake_close)) as mock_close,
        patch.object(PatchrightScraper, "start_browser", AsyncMock(side_effect=fake_start)) as mock_start,
    ):
        await PatchrightScraper.recycle_browser()

    mock_close.assert_awaited_once()
    mock_start.assert_awaited_once()
    assert PatchrightScraper._context is new_context
