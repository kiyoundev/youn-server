"""Tests for PatchrightScraper class-level state behaviour."""

import pytest

from app.services.scraper.patchright_scraper import PatchrightScraper
from app.services.scraper.result import ScraperResult


@pytest.fixture(autouse=True)
def reset_patchright_state():
    """Isolate each test from class-level browser state."""
    original_context = PatchrightScraper._context
    original_playwright = PatchrightScraper._playwright
    PatchrightScraper._context = None
    PatchrightScraper._playwright = None
    yield
    PatchrightScraper._context = original_context
    PatchrightScraper._playwright = original_playwright


@pytest.mark.asyncio
async def test_patchright_no_context_returns_error() -> None:
    result = await PatchrightScraper().get_price("https://example.com/product")
    assert result == ScraperResult(price=None, status="error")


@pytest.mark.asyncio
async def test_start_browser_idempotent() -> None:
    sentinel = object()
    PatchrightScraper._context = sentinel  # type: ignore[assignment]
    await PatchrightScraper.start_browser()
    assert PatchrightScraper._context is sentinel
