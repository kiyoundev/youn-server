"""Tests for RetailerRouter dispatch logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scraper.result import ScraperResult
from app.services.scraper.router import RetailerRouter, _derive_retailer, detect_scraper_type

OK = ScraperResult(price=99.99, status="ok")
OOS = ScraperResult(price=None, status="oos")
ERR = ScraperResult(price=None, status="error")

AMAZON_URL = "https://www.amazon.ca/dp/B0EXAMPLE"
UNKNOWN_URL = "https://bestbuy.ca/en-ca/product/12345"


@pytest.fixture
def router() -> RetailerRouter:
    return RetailerRouter()


@pytest.mark.asyncio
async def test_amazon_routes_to_amazon_scraper(router: RetailerRouter) -> None:
    mock_cls = MagicMock()
    mock_cls.return_value.get_price = AsyncMock(return_value=OK)
    with patch.dict("app.services.scraper.router.RETAILER_MAP", {"amazon.ca": mock_cls}):
        result = await router.get_price(AMAZON_URL)
    assert result == OK
    mock_cls.return_value.get_price.assert_awaited_once_with(AMAZON_URL)


@pytest.mark.asyncio
async def test_amazon_url_with_www_prefix(router: RetailerRouter) -> None:
    mock_cls = MagicMock()
    mock_cls.return_value.get_price = AsyncMock(return_value=OK)
    with patch.dict("app.services.scraper.router.RETAILER_MAP", {"amazon.ca": mock_cls}):
        result = await router.get_price("https://www.amazon.ca/dp/B0")
    assert result == OK


@pytest.mark.asyncio
async def test_scraper_type_patchright_skips_http(router: RetailerRouter) -> None:
    with (
        patch("app.services.scraper.router.HTTPScraper") as MockHTTP,
        patch("app.services.scraper.router.PatchrightScraper") as MockPW,
    ):
        pw_instance = MockPW.return_value
        pw_instance.get_price = AsyncMock(return_value=OK)
        result = await router.get_price(UNKNOWN_URL, scraper_type="patchright")
    MockHTTP.assert_not_called()
    assert result == OK


@pytest.mark.asyncio
async def test_http_ok_no_patchright_fallback(router: RetailerRouter) -> None:
    with (
        patch("app.services.scraper.router.HTTPScraper") as MockHTTP,
        patch("app.services.scraper.router.PatchrightScraper") as MockPW,
    ):
        http_instance = MockHTTP.return_value
        http_instance.get_price = AsyncMock(return_value=OK)
        result = await router.get_price(UNKNOWN_URL)
    MockPW.assert_not_called()
    assert result == OK


@pytest.mark.asyncio
async def test_http_error_falls_back_to_patchright(router: RetailerRouter) -> None:
    with (
        patch("app.services.scraper.router.HTTPScraper") as MockHTTP,
        patch("app.services.scraper.router.PatchrightScraper") as MockPW,
    ):
        http_instance = MockHTTP.return_value
        http_instance.get_price = AsyncMock(return_value=ERR)
        pw_instance = MockPW.return_value
        pw_instance.get_price = AsyncMock(return_value=OK)
        result = await router.get_price(UNKNOWN_URL)
    assert result == OK
    pw_instance.get_price.assert_awaited_once_with(UNKNOWN_URL)


@pytest.mark.asyncio
async def test_http_oos_does_not_fall_back(router: RetailerRouter) -> None:
    with (
        patch("app.services.scraper.router.HTTPScraper") as MockHTTP,
        patch("app.services.scraper.router.PatchrightScraper") as MockPW,
    ):
        http_instance = MockHTTP.return_value
        http_instance.get_price = AsyncMock(return_value=OOS)
        result = await router.get_price(UNKNOWN_URL)
    MockPW.assert_not_called()
    assert result == OOS


@pytest.mark.asyncio
async def test_detect_scraper_type_http_ok_returns_none() -> None:
    with patch("app.services.scraper.router.HTTPScraper") as MockHTTP:
        MockHTTP.return_value.get_price = AsyncMock(return_value=OK)
        result = await detect_scraper_type(UNKNOWN_URL)
    assert result is None


@pytest.mark.asyncio
async def test_detect_scraper_type_http_oos_returns_none() -> None:
    with patch("app.services.scraper.router.HTTPScraper") as MockHTTP:
        MockHTTP.return_value.get_price = AsyncMock(return_value=OOS)
        result = await detect_scraper_type(UNKNOWN_URL)
    assert result is None


@pytest.mark.asyncio
async def test_detect_scraper_type_falls_back_to_patchright() -> None:
    with (
        patch("app.services.scraper.router.HTTPScraper") as MockHTTP,
        patch("app.services.scraper.router.PatchrightScraper") as MockPW,
    ):
        MockHTTP.return_value.get_price = AsyncMock(return_value=ERR)
        MockPW.return_value.get_price = AsyncMock(return_value=OK)
        result = await detect_scraper_type(UNKNOWN_URL)
    assert result == "patchright"


@pytest.mark.asyncio
async def test_detect_scraper_type_raises_when_both_fail() -> None:
    with (
        patch("app.services.scraper.router.HTTPScraper") as MockHTTP,
        patch("app.services.scraper.router.PatchrightScraper") as MockPW,
    ):
        MockHTTP.return_value.get_price = AsyncMock(return_value=ERR)
        MockPW.return_value.get_price = AsyncMock(return_value=ERR)
        with pytest.raises(ValueError):
            await detect_scraper_type(UNKNOWN_URL)


@pytest.mark.parametrize(
    "hostname, expected",
    [
        ("ikea.com", "IKEA"),
        ("29cm.co.kr", "29CM"),
        ("amazon.ca", "Amazon"),
        ("walmart.ca", "Walmart"),
    ],
)
def test_derive_retailer_display_name(hostname: str, expected: str) -> None:
    assert _derive_retailer(hostname) == expected
