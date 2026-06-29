"""Tests for BaseScraper extraction methods and _parse_price."""

import json
import textwrap

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from app.services.scraper.base import BaseScraper, _parse_price
from app.services.scraper.http_scraper import HTTPScraper
from app.services.scraper.result import ScraperResult


class DummyScraper(BaseScraper):
    async def get_price(self, url: str) -> ScraperResult:
        return ScraperResult(price=None, status="error")


@pytest.fixture
def s() -> DummyScraper:
    return DummyScraper()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# _parse_price
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("$1,299.99 CAD", 1299.99),
    ("1 299,99", 1299.99),
    ("CAD 129.99", 129.99),
    ("1.299,99", 1299.99),
    ("129.00", 129.0),
    ("$49", 49.0),
    ("$0.99", 0.99),
    ("1,000.00", 1000.0),
    ("$1,000", 1000.0),
    ("999", 999.0),
    ("", None),
    ("not a price", None),
    ("$0.00", None),
    ("0", None),
])
def test_parse_price(raw: str, expected: float | None) -> None:
    assert _parse_price(raw) == expected


# ---------------------------------------------------------------------------
# _extract_jsonld
# ---------------------------------------------------------------------------

def _jsonld_page(data: dict | list) -> str:
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head></html>'


def test_extract_jsonld_basic_offer(s: DummyScraper) -> None:
    html = _jsonld_page({
        "@type": "Product",
        "offers": {"@type": "Offer", "price": "89.99", "availability": "https://schema.org/InStock"},
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=89.99, status="ok")


def test_extract_jsonld_oos(s: DummyScraper) -> None:
    html = _jsonld_page({
        "@type": "Product",
        "offers": {"@type": "Offer", "price": "89.99", "availability": "https://schema.org/OutOfStock"},
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=None, status="oos")


def test_extract_jsonld_aggregate_offer(s: DummyScraper) -> None:
    html = _jsonld_page({
        "@type": "Product",
        "offers": {"@type": "AggregateOffer", "lowPrice": "49.00", "highPrice": "99.00"},
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=49.0, status="ok")


def test_extract_jsonld_graph(s: DummyScraper) -> None:
    html = _jsonld_page({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite"},
            {"@type": "Product", "offers": {"@type": "Offer", "price": "199.00"}},
        ],
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=199.0, status="ok")


def test_extract_jsonld_array(s: DummyScraper) -> None:
    html = _jsonld_page([
        {"@type": "BreadcrumbList"},
        {"@type": "Product", "offers": {"@type": "Offer", "price": "55.00"}},
    ])
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=55.0, status="ok")


def test_extract_jsonld_no_product_returns_none(s: DummyScraper) -> None:
    html = _jsonld_page({"@type": "WebSite", "url": "https://example.com"})
    assert s._extract_jsonld(_soup(html)) is None


def test_extract_jsonld_invalid_json_skipped(s: DummyScraper) -> None:
    html = textwrap.dedent("""\
        <html><head>
        <script type="application/ld+json">NOT JSON</script>
        <script type="application/ld+json">{"@type": "Product", "offers": {"price": "10.00"}}</script>
        </head></html>
    """)
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=10.0, status="ok")


def test_extract_jsonld_no_scripts_returns_none(s: DummyScraper) -> None:
    assert s._extract_jsonld(_soup("<html><body>nothing</body></html>")) is None


# ---------------------------------------------------------------------------
# _extract_og_price
# ---------------------------------------------------------------------------

def test_extract_og_price_standard(s: DummyScraper) -> None:
    html = '<html><head><meta property="og:price:amount" content="129.00"></head></html>'
    assert s._extract_og_price(_soup(html)) == ScraperResult(price=129.0, status="ok")


def test_extract_og_price_product_ns(s: DummyScraper) -> None:
    html = '<html><head><meta property="product:price:amount" content="49.99"></head></html>'
    assert s._extract_og_price(_soup(html)) == ScraperResult(price=49.99, status="ok")


def test_extract_og_price_missing_returns_none(s: DummyScraper) -> None:
    html = '<html><head><title>No price</title></head></html>'
    assert s._extract_og_price(_soup(html)) is None


def test_extract_og_price_empty_content_returns_none(s: DummyScraper) -> None:
    html = '<html><head><meta property="og:price:amount" content=""></head></html>'
    assert s._extract_og_price(_soup(html)) is None


# ---------------------------------------------------------------------------
# _extract_nextdata
# ---------------------------------------------------------------------------

def _nextdata_page(data: dict) -> str:
    return f'<html><body><script id="__NEXT_DATA__">{json.dumps(data)}</script></body></html>'


def test_extract_nextdata_heuristic(s: DummyScraper) -> None:
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 550.0}}}})
    result = s._extract_nextdata(_soup(html), "https://ssense.com/products/test")
    assert result == ScraperResult(price=550.0, status="ok")


def test_extract_nextdata_explicit_path(s: DummyScraper, monkeypatch) -> None:
    import app.services.scraper.config as cfg
    monkeypatch.setitem(cfg.NEXTDATA_PATHS, "ssense.com", ["props", "pageProps", "product", "price"])
    import app.services.scraper.base as base_mod
    monkeypatch.setattr(base_mod, "NEXTDATA_PATHS", cfg.NEXTDATA_PATHS)
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 550.0}}}})
    result = s._extract_nextdata(_soup(html), "https://ssense.com/products/test")
    assert result == ScraperResult(price=550.0, status="ok")


def test_extract_nextdata_no_price_returns_none(s: DummyScraper) -> None:
    html = _nextdata_page({"props": {"pageProps": {"name": "widget"}}})
    assert s._extract_nextdata(_soup(html), "https://example.com/product") is None


def test_extract_nextdata_no_script_returns_none(s: DummyScraper) -> None:
    assert s._extract_nextdata(_soup("<html><body>nothing</body></html>"), "https://example.com") is None


def test_extract_nextdata_bad_explicit_path_falls_back_to_heuristic(s: DummyScraper, monkeypatch) -> None:
    import app.services.scraper.base as base_mod
    monkeypatch.setattr(base_mod, "NEXTDATA_PATHS", {"example.com": ["nonexistent", "key"]})
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 75.0}}}})
    result = s._extract_nextdata(_soup(html), "https://example.com/product/item")
    assert result == ScraperResult(price=75.0, status="ok")


# ---------------------------------------------------------------------------
# _extract_shopify
# ---------------------------------------------------------------------------

SHOPIFY_RESPONSE = {
    "product": {
        "variants": [
            {"id": 111, "price": "129.00", "available": True},
            {"id": 222, "price": "149.00", "available": False},
        ]
    }
}


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_default_variant(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90")
    assert result == ScraperResult(price=129.0, status="ok")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_specific_variant(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90?variant=222")
    assert result == ScraperResult(price=None, status="oos")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_404_returns_none(s: DummyScraper) -> None:
    respx.get("https://example.com/products/widget.json").mock(
        return_value=httpx.Response(404)
    )
    result = await s._extract_shopify("", "https://example.com/products/widget")
    assert result is None


@pytest.mark.asyncio
async def test_extract_shopify_non_product_url_returns_none(s: DummyScraper) -> None:
    result = await s._extract_shopify("", "https://example.com/collections/sale")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_non_shopify_json_returns_none(s: DummyScraper) -> None:
    respx.get("https://example.com/products/widget.json").mock(
        return_value=httpx.Response(200, json={"error": "not found"})
    )
    result = await s._extract_shopify("", "https://example.com/products/widget")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_html_suffix_stripped(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90.html")
    assert result == ScraperResult(price=129.0, status="ok")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_empty_variants_returns_none(s: DummyScraper) -> None:
    respx.get("https://example.com/products/widget.json").mock(
        return_value=httpx.Response(200, json={"product": {"variants": []}})
    )
    result = await s._extract_shopify("", "https://example.com/products/widget")
    assert result is None


# ---------------------------------------------------------------------------
# _run_hierarchy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_run_hierarchy_shopify_wins(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/widget.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    html = _jsonld_page({"@type": "Product", "offers": {"price": "999.00"}})
    result = await s._run_hierarchy(html, "https://deadstock.ca/products/widget")
    assert result == ScraperResult(price=129.0, status="ok")


@pytest.mark.asyncio
async def test_run_hierarchy_fallthrough_to_error(s: DummyScraper) -> None:
    result = await s._run_hierarchy("<html><body>nothing</body></html>", "https://example.com/product")
    assert result == ScraperResult(price=None, status="error")


@pytest.mark.asyncio
async def test_run_hierarchy_jsonld_wins(s: DummyScraper) -> None:
    html = _jsonld_page({"@type": "Product", "offers": {"price": "89.99"}})
    result = await s._run_hierarchy(html, "https://bestbuy.ca/en-ca/product/12345")
    assert result == ScraperResult(price=89.99, status="ok")


@pytest.mark.asyncio
async def test_run_hierarchy_og_wins(s: DummyScraper) -> None:
    html = '<html><head><meta property="og:price:amount" content="49.99"></head></html>'
    result = await s._run_hierarchy(html, "https://example.com/item/abc")
    assert result == ScraperResult(price=49.99, status="ok")


@pytest.mark.asyncio
async def test_run_hierarchy_nextdata_wins(s: DummyScraper) -> None:
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 299.0}}}})
    result = await s._run_hierarchy(html, "https://example.com/item/abc")
    assert result == ScraperResult(price=299.0, status="ok")


# ---------------------------------------------------------------------------
# HTTPScraper end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_http_scraper_jsonld_page() -> None:
    page_html = _jsonld_page({"@type": "Product", "offers": {"price": "89.99"}})
    respx.get("https://bestbuy.ca/en-ca/product/12345").mock(
        return_value=httpx.Response(200, text=page_html)
    )
    result = await HTTPScraper().get_price("https://bestbuy.ca/en-ca/product/12345")
    assert result == ScraperResult(price=89.99, status="ok")


@pytest.mark.asyncio
@respx.mock
async def test_http_scraper_connection_error_returns_error() -> None:
    respx.get("http://localhost:9999/nope").mock(side_effect=httpx.ConnectError("refused"))
    result = await HTTPScraper().get_price("http://localhost:9999/nope")
    assert result == ScraperResult(price=None, status="error")
