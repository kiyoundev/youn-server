"""Tests for BaseScraper extraction methods and _parse_price."""

import json
import textwrap

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from app.services.scraper.base import (
    BaseScraper,
    _describe_exception,
    _detect_bot_block,
    _detect_currency,
    _extract_currency,
    _extract_id_from_url,
    _extract_product_title,
    _extract_site_name,
    _find_node_by_id,
    _first_title_segment,
    _last_title_segment,
    _parse_price,
    _parse_rsc_flight_rows,
    _resolve_rsc_refs,
    _split_title,
    _strip_trailing_site_name,
)
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
    """Issue #68 — the page's listed price is kept alongside "oos"."""
    html = _jsonld_page({
        "@type": "Product",
        "offers": {"@type": "Offer", "price": "89.99", "availability": "https://schema.org/OutOfStock"},
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=89.99, status="oos")


@pytest.mark.parametrize(
    "availability",
    ["https://schema.org/SoldOut", "https://schema.org/Discontinued", "SoldOut"],
)
def test_extract_jsonld_sold_out_and_discontinued_are_oos(s: DummyScraper, availability: str) -> None:
    html = _jsonld_page({
        "@type": "Product",
        "offers": {"@type": "Offer", "price": "89.99", "availability": availability},
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=89.99, status="oos")


@pytest.mark.parametrize(
    "availability",
    ["https://schema.org/InStock", "https://schema.org/PreOrder", "https://schema.org/BackOrder"],
)
def test_extract_jsonld_other_availability_values_keep_price(s: DummyScraper, availability: str) -> None:
    html = _jsonld_page({
        "@type": "Product",
        "offers": {"@type": "Offer", "price": "89.99", "availability": availability},
    })
    assert s._extract_jsonld(_soup(html)) == ScraperResult(price=89.99, status="ok")


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


@pytest.mark.parametrize(
    "availability_prop, value",
    [
        ("og:availability", "out of stock"),
        ("product:availability", "out of stock"),
        ("product:availability", "OutOfStock"),
        ("og:availability", "oos"),
        ("og:availability", "Sold Out"),
        ("og:availability", "https://schema.org/OutOfStock"),
    ],
)
def test_extract_og_price_out_of_stock_availability(
    s: DummyScraper, availability_prop: str, value: str
) -> None:
    html = (
        '<html><head><meta property="og:price:amount" content="129.00">'
        f'<meta property="{availability_prop}" content="{value}"></head></html>'
    )
    assert s._extract_og_price(_soup(html)) == ScraperResult(price=129.0, status="oos")


@pytest.mark.parametrize("value", ["in stock", "instock", "available for order"])
def test_extract_og_price_in_stock_availability_keeps_price(s: DummyScraper, value: str) -> None:
    html = (
        '<html><head><meta property="og:price:amount" content="129.00">'
        f'<meta property="product:availability" content="{value}"></head></html>'
    )
    assert s._extract_og_price(_soup(html)) == ScraperResult(price=129.0, status="ok")


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
# _extract_nextdata — priority-key search + ID scoping (musinsa regression)
#
# Real shape from musinsa.com/products/5622799 (Endure Goose Down Jacket,
# dark grey): the product's own node carries salePrice/normalPrice/
# couponPrice/finalPrice together, and a "same jacket, other colors"
# carousel elsewhere on the page repeats those same field names for
# different goodsNo values — one of which (black) has no discount at all,
# so grabbing the wrong node's finalPrice wouldn't even look implausible.
# ---------------------------------------------------------------------------

def _musinsa_like_page(tracked_final_price: int) -> dict:
    return {
        "props": {
            "pageProps": {
                # Real page order: unrelated scalar fields, then "meta"
                # (the tracked product), then "dehydratedState" (carries the
                # carousel) — kept in that order here since one regression
                # test below depends on scoping working regardless of it.
                "isMobile": False,
                "meta": {
                    "data": {
                        "goodsNo": 5622799,
                        "goodsNm": "인듀어 구스 다운 자켓 (다크 그레이)",
                        "goodsPrice": {
                            "salePrice": 310400,
                            "normalPrice": 388000,
                            "couponPrice": 279360,
                            "finalPrice": tracked_final_price,
                            "finalDiscount": 28,
                        },
                    }
                },
                "dehydratedState": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "data": {
                                        "curationTabs": [
                                            {
                                                "curationGoodsList": [
                                                    {"goodsNo": 5622799, "finalPrice": tracked_final_price, "normalPrice": 388000},
                                                    {"goodsNo": 5622834, "finalPrice": tracked_final_price, "normalPrice": 388000},
                                                    # Different product, no discount — proves scoping
                                                    # isn't just "first plausible finalPrice in the tree".
                                                    {"goodsNo": 5622697, "finalPrice": 388000, "normalPrice": 388000},
                                                ]
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    ]
                },
            }
        }
    }


def test_extract_nextdata_prefers_final_price_over_plain_price(s: DummyScraper) -> None:
    html = _nextdata_page(_musinsa_like_page(279360))
    result = s._extract_nextdata(_soup(html), "https://www.musinsa.com/products/5622799")
    assert result == ScraperResult(price=279360.0, status="ok")


def test_extract_nextdata_id_scoping_ignores_other_products_carousel(s: DummyScraper) -> None:
    # Same tree, but the tracked product's own finalPrice differs from the
    # (unrelated) carousel's black-variant entry (388000, no discount) —
    # scoping to goodsNo 5622799 must return the tracked product's own
    # price, not whichever finalPrice DFS would hit first unscoped.
    page = _musinsa_like_page(279360)
    page["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["data"]["curationTabs"][0][
        "curationGoodsList"
    ].insert(0, {"goodsNo": 9999999, "finalPrice": 111111, "normalPrice": 111111})
    html = _nextdata_page(page)
    result = s._extract_nextdata(_soup(html), "https://www.musinsa.com/products/5622799")
    assert result == ScraperResult(price=279360.0, status="ok")


def test_extract_nextdata_priority_falls_back_to_bare_price(s: DummyScraper) -> None:
    """Pages with only a plain "price" field (no finalPrice/salePrice/etc.)
    keep working exactly as before — priority list ends in "price"."""
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 42.0}}}})
    result = s._extract_nextdata(_soup(html), "https://example.com/products/1")
    assert result == ScraperResult(price=42.0, status="ok")


def test_extract_id_from_url_last_numeric_segment() -> None:
    assert _extract_id_from_url("https://www.musinsa.com/products/5622799") == "5622799"
    assert _extract_id_from_url("https://www.musinsa.com/products/5622799?color=grey") == "5622799"
    assert _extract_id_from_url("https://example.com/p/not-numeric") is None
    assert _extract_id_from_url("https://example.com/") is None


def test_find_node_by_id_matches_any_candidate_key() -> None:
    tree = {"a": {"items": [{"sku": "X"}, {"productId": "42", "price": 9}]}}
    node = _find_node_by_id(tree, "42")
    assert node == {"productId": "42", "price": 9}
    assert _find_node_by_id(tree, "does-not-exist") is None


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
async def test_extract_shopify_keeps_locale_prefix(s: DummyScraper) -> None:
    """dickies.com/en-ca/... must fetch /en-ca/products/{handle}.json — the
    bare /products/ path is the default (USD) market, $39.99 USD instead of
    $61.00 CAD for the same pants."""
    respx.get("https://www.dickies.com/en-ca/products/carpenter-pants.json").mock(
        return_value=httpx.Response(200, json={"product": {"variants": [{"id": 1, "price": "61.00"}]}})
    )
    bare = respx.get("https://www.dickies.com/products/carpenter-pants.json").mock(
        return_value=httpx.Response(200, json={"product": {"variants": [{"id": 1, "price": "39.99"}]}})
    )
    result = await s._extract_shopify("", "https://www.dickies.com/en-ca/products/carpenter-pants")
    assert result == ScraperResult(price=61.0, status="ok")
    assert not bare.called


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_specific_variant(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90?variant=222")
    assert result == ScraperResult(price=149.0, status="oos")


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


# .js (documented Ajax Product API): top-level product, prices in integer cents.
SHOPIFY_JS_RESPONSE = {
    "id": 1,
    "available": True,
    "variants": [
        {"id": 111, "price": 12900, "available": True},
        {"id": 222, "price": 14900, "available": False},
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_preferred_over_json(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.js").mock(
        return_value=httpx.Response(200, json=SHOPIFY_JS_RESPONSE)
    )
    json_route = respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90")
    assert result == ScraperResult(price=129.0, status="ok")
    assert not json_route.called


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_sold_out_variant_is_oos(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.js").mock(
        return_value=httpx.Response(200, json=SHOPIFY_JS_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90?variant=222")
    assert result == ScraperResult(price=149.0, status="oos")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_keeps_locale_prefix(s: DummyScraper) -> None:
    respx.get("https://www.dickies.com/en-ca/products/carpenter-pants.js").mock(
        return_value=httpx.Response(200, json={"variants": [{"id": 1, "price": 6100, "available": True}]})
    )
    bare = respx.get("https://www.dickies.com/products/carpenter-pants.js").mock(
        return_value=httpx.Response(200, json={"variants": [{"id": 1, "price": 3999, "available": True}]})
    )
    result = await s._extract_shopify("", "https://www.dickies.com/en-ca/products/carpenter-pants")
    assert result == ScraperResult(price=61.0, status="ok")
    assert not bare.called


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_variant_without_flag_uses_product_level_available(s: DummyScraper) -> None:
    respx.get("https://example.com/products/widget.js").mock(
        return_value=httpx.Response(200, json={"available": False, "variants": [{"id": 1, "price": 5000}]})
    )
    result = await s._extract_shopify("", "https://example.com/products/widget")
    assert result == ScraperResult(price=50.0, status="oos")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_no_variant_skips_sold_out_first_size(s: DummyScraper) -> None:
    """Real Dickies shape: first size sold out, later ones in stock. A URL
    without ?variant= names the color, so it is in stock at the first
    buyable size's price, not out of stock."""
    respx.get("https://www.dickies.com/en-ca/products/carpenter-pants.js").mock(
        return_value=httpx.Response(
            200,
            json={
                "available": True,
                "variants": [
                    {"id": 1, "price": 6100, "available": False},
                    {"id": 2, "price": 6100, "available": True},
                    {"id": 3, "price": 6100, "available": True},
                ],
            },
        )
    )
    result = await s._extract_shopify("", "https://www.dickies.com/en-ca/products/carpenter-pants")
    assert result == ScraperResult(price=61.0, status="ok")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_no_variant_all_sold_out_is_oos(s: DummyScraper) -> None:
    respx.get("https://example.com/products/widget.js").mock(
        return_value=httpx.Response(
            200,
            json={
                "available": False,
                "variants": [
                    {"id": 1, "price": 5000, "available": False},
                    {"id": 2, "price": 5000, "available": False},
                ],
            },
        )
    )
    result = await s._extract_shopify("", "https://example.com/products/widget")
    assert result == ScraperResult(price=50.0, status="oos")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_js_specific_sold_out_size_is_oos_even_if_others_in_stock(
    s: DummyScraper,
) -> None:
    respx.get("https://www.dickies.com/en-ca/products/carpenter-pants.js").mock(
        return_value=httpx.Response(
            200,
            json={
                "available": True,
                "variants": [
                    {"id": 1, "price": 6100, "available": False},
                    {"id": 2, "price": 6100, "available": True},
                ],
            },
        )
    )
    result = await s._extract_shopify("", "https://www.dickies.com/en-ca/products/carpenter-pants?variant=1")
    assert result == ScraperResult(price=61.0, status="oos")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_falls_back_to_json_when_js_fails(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.js").mock(return_value=httpx.Response(404))
    respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90")
    assert result == ScraperResult(price=129.0, status="ok")


@pytest.mark.asyncio
@respx.mock
async def test_extract_shopify_falls_back_to_json_when_js_is_not_json(s: DummyScraper) -> None:
    respx.get("https://deadstock.ca/products/nike-air-max-90.js").mock(
        return_value=httpx.Response(200, text="<html>blocked</html>")
    )
    respx.get("https://deadstock.ca/products/nike-air-max-90.json").mock(
        return_value=httpx.Response(200, json=SHOPIFY_RESPONSE)
    )
    result = await s._extract_shopify("", "https://deadstock.ca/products/nike-air-max-90")
    assert result == ScraperResult(price=129.0, status="ok")


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
    assert result == ScraperResult(price=129.0, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_fallthrough_to_error(s: DummyScraper) -> None:
    result = await s._run_hierarchy("<html><body>nothing</body></html>", "https://example.com/product")
    assert result == ScraperResult(price=None, status="error", currency="CAD", error_reason="no price found on page")


# Real page shape captured from issue #52 — Crate & Barrel behind Akamai.
AKAMAI_DENY_HTML = (
    "<html><head><title>Access Denied</title></head><body><h1>Access Denied</h1>"
    "You don't have permission to access \"http://www.crateandbarrel.ca/x\" on this server."
    "<p>Reference #18.45a71002.1789660259.a824f66f</p>"
    "<p>https://errors.edgesuite.net/18.45a71002.1789660259.a824f66f</p></body></html>"
)


@pytest.mark.asyncio
async def test_run_hierarchy_error_reason_names_akamai_block(s: DummyScraper) -> None:
    result = await s._run_hierarchy(AKAMAI_DENY_HTML, "https://www.crateandbarrel.ca/x")
    assert result.status == "error"
    assert result.error_reason == "Akamai bot-block (access denied)"


@pytest.mark.asyncio
async def test_run_hierarchy_error_reason_names_cloudflare_challenge(s: DummyScraper) -> None:
    html = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
    result = await s._run_hierarchy(html, "https://example.com/p")
    assert result.status == "error"
    assert result.error_reason == "Cloudflare bot-check challenge did not clear"


@pytest.mark.asyncio
async def test_run_hierarchy_success_carries_no_error_reason(s: DummyScraper) -> None:
    html = _jsonld_page({"@type": "Product", "offers": {"price": "129.00"}})
    result = await s._run_hierarchy(html, "https://example.com/product")
    assert result.status == "ok"
    assert result.error_reason is None


# Issue #64 — metadata is applied for every status, so the generic path must
# only attach what the page can vouch for.

_PAGE_META_HEAD = (
    '<title>Widget Pro | Acme</title>'
    '<meta property="og:site_name" content="Acme">'
)


@pytest.mark.asyncio
async def test_run_hierarchy_oos_keeps_name_site_and_currency(s: DummyScraper) -> None:
    ld = json.dumps(
        {
            "@type": "Product",
            "name": "Widget Pro",
            "offers": {"@type": "Offer", "price": "89.99", "availability": "https://schema.org/OutOfStock"},
        }
    )
    html = (
        f'<html><head>{_PAGE_META_HEAD}<script type="application/ld+json">{ld}</script></head></html>'
    )
    result = await s._run_hierarchy(html, "https://acme.ca/p/widget")
    assert result.status == "oos"
    assert result.product_title == "Widget Pro"
    assert result.site_name == "Acme"
    assert result.currency == "CAD"
    assert result.price == 89.99  # issue #68 — listed price kept on oos


@pytest.mark.asyncio
async def test_run_hierarchy_bot_block_carries_no_metadata(s: DummyScraper) -> None:
    """A block page has a <title> and a currency heuristic of its own — none
    of it may reach the product (name inference is first-write-wins)."""
    for html in (
        AKAMAI_DENY_HTML,
        '<html><head><title>Just a moment...</title><meta property="og:site_name" content="Cloudflare"></head>'
        "<body>Checking your browser</body></html>",
    ):
        result = await s._run_hierarchy(html, "https://example.com/p")
        assert result.status == "error"
        assert result.product_title is None
        assert result.site_name is None
        assert result.currency is None


@pytest.mark.asyncio
async def test_run_hierarchy_unrecognised_error_page_withholds_name_and_site_keeps_currency(
    s: DummyScraper,
) -> None:
    """A 404 / login wall is no bot-block signature, but it is not the
    product either: its title must not become the product's permanent name."""
    html = f"<html><head>{_PAGE_META_HEAD.replace('Widget Pro', 'Page Not Found')}</head><body>404</body></html>"
    result = await s._run_hierarchy(html, "https://acme.ca/p/gone")
    assert result.status == "error"
    assert result.product_title is None
    assert result.site_name is None
    assert result.currency == "CAD"


def test_detect_bot_block_ignores_access_denied_without_akamai_markers() -> None:
    """Some other vendor's (or a site's own) "Access Denied" page must not
    be mislabeled as Akamai — falls through to the caller's generic reason."""
    soup = BeautifulSoup("<html><head><title>Access Denied</title></head><body>nope</body></html>", "html.parser")
    assert _detect_bot_block(soup) is None


def test_detect_bot_block_none_for_normal_page_and_missing_title() -> None:
    assert _detect_bot_block(BeautifulSoup("<html><head><title>Widget</title></head></html>", "html.parser")) is None
    assert _detect_bot_block(BeautifulSoup("<html><body>no title</body></html>", "html.parser")) is None


def test_describe_exception_includes_type_and_message() -> None:
    assert _describe_exception(httpx.ConnectError("refused")) == "ConnectError: refused"


def test_describe_exception_empty_message_falls_back_to_type_name() -> None:
    """str(TimeoutError()) is "" — persisting that would violate the
    non-empty-reason guarantee."""
    assert _describe_exception(TimeoutError()) == "TimeoutError"
    assert _describe_exception(httpx.ConnectError("")) == "ConnectError"


def test_describe_exception_keeps_only_first_line() -> None:
    exc = TimeoutError("Page.goto: Timeout 30000ms exceeded.\nCall log:\n  - navigating to ...")
    assert _describe_exception(exc) == "TimeoutError: Page.goto: Timeout 30000ms exceeded."


def test_describe_exception_truncates_long_messages() -> None:
    result = _describe_exception(RuntimeError("x" * 500))
    assert len(result) == 200
    assert result.endswith("…")


@pytest.mark.asyncio
async def test_run_hierarchy_jsonld_wins(s: DummyScraper) -> None:
    html = _jsonld_page({"@type": "Product", "offers": {"price": "89.99"}})
    result = await s._run_hierarchy(html, "https://bestbuy.ca/en-ca/product/12345")
    assert result == ScraperResult(price=89.99, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_og_wins(s: DummyScraper) -> None:
    html = '<html><head><meta property="og:price:amount" content="49.99"></head></html>'
    result = await s._run_hierarchy(html, "https://example.com/item/abc")
    assert result == ScraperResult(price=49.99, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_nextdata_wins(s: DummyScraper) -> None:
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 299.0}}}})
    result = await s._run_hierarchy(html, "https://example.com/item/abc")
    assert result == ScraperResult(price=299.0, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_nextdata_overrides_og_price_when_cheaper(s: DummyScraper) -> None:
    """musinsa regression (this session) — og:price meta reports the plain
    sale price with no coupon awareness; __NEXT_DATA__'s goodsPrice has the
    actual stacked-coupon finalPrice alongside it. NEXT_DATA is now checked
    unconditionally (not just as a last-resort fallback) and its strictly
    cheaper match overrides og:price's cruder one."""
    html = (
        '<html><head><meta property="og:price:amount" content="310400"></head>'
        "<body><script id=\"__NEXT_DATA__\">"
        + json.dumps(
            {
                "props": {
                    "pageProps": {
                        "meta": {
                            "data": {
                                "goodsNo": 5622799,
                                "goodsPrice": {
                                    "salePrice": 310400,
                                    "normalPrice": 388000,
                                    "couponPrice": 279360,
                                    "finalPrice": 279360,
                                },
                            }
                        }
                    }
                }
            }
        )
        + "</script></body></html>"
    )
    result = await s._run_hierarchy(html, "https://www.musinsa.com/products/5622799")
    assert result == ScraperResult(price=279360.0, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_og_price_wins_when_cheaper_than_nextdata(s: DummyScraper) -> None:
    """Override only fires when NEXT_DATA is strictly cheaper — a page
    where NEXT_DATA's own price happens to be higher than what an earlier
    method already found keeps that earlier (cheaper) result, not the
    higher NEXT_DATA one."""
    html = (
        '<html><head><meta property="og:price:amount" content="49.99"></head>'
        "<body><script id=\"__NEXT_DATA__\">"
        + json.dumps({"props": {"pageProps": {"product": {"price": 99.99}}}})
        + "</script></body></html>"
    )
    result = await s._run_hierarchy(html, "https://example.com/item/abc")
    assert result == ScraperResult(price=49.99, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_logs_og_price_extractor(
    s: DummyScraper, caplog: pytest.LogCaptureFixture
) -> None:
    html = '<html><head><meta property="og:price:amount" content="49.99"></head></html>'
    with caplog.at_level("INFO", logger="app.services.scraper.base"):
        await s._run_hierarchy(html, "https://example.com/item/abc")
    assert (
        "extractor=og_price status=ok price=49.99 currency=CAD currency_source=default "
        "url=https://example.com/item/abc"
        in caplog.text
    )


@pytest.mark.asyncio
async def test_run_hierarchy_logs_nextdata_when_it_overrides(
    s: DummyScraper, caplog: pytest.LogCaptureFixture
) -> None:
    html = (
        '<html><head><meta property="og:price:amount" content="99.99"></head>'
        "<body><script id=\"__NEXT_DATA__\">"
        + json.dumps({"props": {"pageProps": {"product": {"id": 123, "price": 49.99}}}})
        + "</script></body></html>"
    )
    with caplog.at_level("INFO", logger="app.services.scraper.base"):
        await s._run_hierarchy(html, "https://example.com/item/123")
    assert "extractor=next_data status=ok price=49.99" in caplog.text


@pytest.mark.asyncio
async def test_run_hierarchy_logs_none_when_nothing_matches(
    s: DummyScraper, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="app.services.scraper.base"):
        await s._run_hierarchy("<html><body>nothing</body></html>", "https://example.com/item/abc")
    assert "extractor=none status=error price=None" in caplog.text


@pytest.mark.asyncio
async def test_run_hierarchy_unscoped_nextdata_does_not_override_earlier_price(
    s: DummyScraper, caplog: pytest.LogCaptureFixture
) -> None:
    """Slug URL (no numeric id) -> whole-page search, which can land on an
    add-on or carousel item. A cheaper unscoped match must not replace the
    price an earlier tier found."""
    html = (
        '<html><head><meta property="og:price:amount" content="120.00"></head>'
        "<body><script id=\"__NEXT_DATA__\">"
        + json.dumps({"props": {"pageProps": {"giftAddOn": {"salePrice": 8}}}})
        + "</script></body></html>"
    )
    with caplog.at_level("INFO", logger="app.services.scraper.base"):
        result = await s._run_hierarchy(html, "https://shop.example.com/products/blue-jacket")
    assert result.price == 120.0
    assert "ignored unscoped next_data price 8.0 (keeping 120.0 from og_price)" in caplog.text


@pytest.mark.asyncio
async def test_run_hierarchy_unscoped_nextdata_still_fills_in_when_nothing_earlier(s: DummyScraper) -> None:
    html = _nextdata_page({"props": {"pageProps": {"product": {"price": 299.0}}}})
    result = await s._run_hierarchy(html, "https://shop.example.com/products/blue-jacket")
    assert result == ScraperResult(price=299.0, status="ok", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_scoped_nextdata_still_overrides_earlier_price(s: DummyScraper) -> None:
    html = (
        '<html><head><meta property="og:price:amount" content="120.00"></head>'
        "<body><script id=\"__NEXT_DATA__\">"
        + json.dumps({"props": {"pageProps": {"product": {"id": 555, "finalPrice": 90}}}})
        + "</script></body></html>"
    )
    result = await s._run_hierarchy(html, "https://shop.example.com/products/555")
    assert result.price == 90.0


@pytest.mark.asyncio
async def test_run_hierarchy_unscoped_rsc_does_not_override_earlier_price(s: DummyScraper) -> None:
    html = _rsc_page({"a7": {"totalDiscountedItemPrice": 800}}).replace(
        "<html><body>",
        '<html><head><meta property="og:price:amount" content="12000"></head><body>',
        1,
    )
    result = await s._run_hierarchy(html, "https://www.29cm.co.kr/products/9999999")
    assert result.price == 12000.0


@pytest.mark.asyncio
async def test_run_hierarchy_unscoped_rsc_still_fills_in_when_nothing_earlier(s: DummyScraper) -> None:
    html = _rsc_page({"a7": {"totalDiscountedItemPrice": 800}})
    result = await s._run_hierarchy(html, "https://www.29cm.co.kr/products/9999999")
    assert result.price == 800.0


@pytest.mark.asyncio
async def test_run_hierarchy_og_out_of_stock_is_not_overridden(s: DummyScraper) -> None:
    html = (
        '<html><head><meta property="og:price:amount" content="99.99">'
        '<meta property="product:availability" content="out of stock"></head>'
        "<body><script id=\"__NEXT_DATA__\">"
        + json.dumps({"props": {"pageProps": {"product": {"price": 49.99}}}})
        + "</script></body></html>"
    )
    result = await s._run_hierarchy(html, "https://example.com/item/abc")
    # Only an in-stock ("ok") result may be replaced by a cheaper scoped
    # NEXT_DATA match — the oos result keeps its status and its listed price
    # (issue #68; previously it had price=None, which skipped the override).
    assert result.status == "oos"
    assert result.price == 99.99


# ---------------------------------------------------------------------------
# _extract_rsc_flight / _parse_rsc_flight_rows / _resolve_rsc_refs
# (issue #50 — 29CM regression)
#
# Real shape from 29cm.co.kr/products/3567244 (same jacket as the musinsa
# fixtures above): no __NEXT_DATA__ tag at all (App Router) — data ships as
# a stream of self.__next_f.push([1, "{id}:{json}"]) calls instead. The
# tracked product's own row ("3c" on the real page) carries the URL's id
# (itemNo) alongside a *reference* to a separate row ("internalDisplayPrice:
# "$a7"") rather than the price inline — row "a7" is where
# totalDiscountedItemPrice actually lives.
# ---------------------------------------------------------------------------

def _rsc_page(rows: dict, *, split_row: str | None = None) -> str:
    """One self.__next_f.push(...) script per row — "{id}:{json}\\n" per
    push call, matching the common case. The trailing newline matters:
    real Flight rows are newline-terminated within the decoded chunk text
    (confirmed against 29CM's actual page — concatenated chunks split on
    "\\n(?=[hex]:)"), so omitting it here would merge rows into one
    unparseable blob instead of reproducing the real boundary. If
    split_row names a key in rows, that row's payload is emitted across
    two separate push calls instead of one, covering the real "a single
    row can span multiple chunks" behavior confirmed against that page."""
    scripts = []
    for row_id, value in rows.items():
        row_text = f"{row_id}:{json.dumps(value)}\n"
        if row_id == split_row:
            mid = len(row_text) // 2
            scripts.append(f"<script>self.__next_f.push({json.dumps([1, row_text[:mid]])})</script>")
            scripts.append(f"<script>self.__next_f.push({json.dumps([1, row_text[mid:]])})</script>")
        else:
            scripts.append(f"<script>self.__next_f.push({json.dumps([1, row_text])})</script>")
    return "<html><body>" + "".join(scripts) + "</body></html>"


def test_parse_rsc_flight_rows_no_chunks_returns_empty(s: DummyScraper) -> None:
    assert _parse_rsc_flight_rows("<html><body>plain page</body></html>") == {}


def test_resolve_rsc_refs_follows_reference_to_sibling_row() -> None:
    rows = {"3c": {"internalDisplayPrice": "$a7"}, "a7": {"totalDiscountedItemPrice": 329800}}
    resolved = _resolve_rsc_refs(rows["3c"], rows)
    assert resolved == {"internalDisplayPrice": {"totalDiscountedItemPrice": 329800}}


def test_resolve_rsc_refs_leaves_unmatched_string_alone() -> None:
    rows: dict = {}
    assert _resolve_rsc_refs("just a plain string", rows) == "just a plain string"
    assert _resolve_rsc_refs("$doesnotexist", rows) == "$doesnotexist"


def test_extract_rsc_flight_resolves_reference_to_find_price(s: DummyScraper) -> None:
    """29CM regression — the tracked product's own row has itemNo (matches
    the URL's id) plus a reference to a separate row holding the actual
    discounted price, not the price inline."""
    html = _rsc_page(
        {
            "3c": {"itemNo": 3567244, "sellPrice": 388000, "internalDisplayPrice": "$a7"},
            "a7": {"totalDiscountedItemPrice": 329800, "totalDiscountedRate": 15},
        }
    )
    result = s._extract_rsc_flight(html, "https://www.29cm.co.kr/products/3567244")
    assert result == ScraperResult(price=329800.0, status="ok")


def test_extract_rsc_flight_row_split_across_multiple_pushes(s: DummyScraper) -> None:
    """A single row's payload can be split across separate push() calls —
    must be concatenated in document order before splitting into rows,
    not parsed push-by-push (confirmed against 29CM's real page)."""
    html = _rsc_page(
        {
            "3c": {"itemNo": 3567244, "internalDisplayPrice": "$a7"},
            "a7": {"totalDiscountedItemPrice": 329800},
        },
        split_row="3c",
    )
    result = s._extract_rsc_flight(html, "https://www.29cm.co.kr/products/3567244")
    assert result == ScraperResult(price=329800.0, status="ok")


def test_extract_rsc_flight_falls_back_unscoped_when_id_unmatched(s: DummyScraper) -> None:
    """No row carries a matching id — falls back to searching every row
    directly, same graceful-degradation shape as _extract_nextdata's own
    id-scoping fallback."""
    html = _rsc_page({"a7": {"totalDiscountedItemPrice": 329800}})
    result = s._extract_rsc_flight(html, "https://www.29cm.co.kr/products/9999999")
    assert result == ScraperResult(price=329800.0, status="ok")


def test_extract_rsc_flight_no_chunks_returns_none(s: DummyScraper) -> None:
    result = s._extract_rsc_flight("<html><body>plain page</body></html>", "https://example.com/products/1")
    assert result is None


@pytest.mark.asyncio
async def test_run_hierarchy_rsc_overrides_jsonld_when_cheaper(s: DummyScraper) -> None:
    """29CM regression, full hierarchy — JSON-LD reports the list price
    (what today's code found before this fix); RSC/Flight rows have the
    real coupon-discounted price. RSC is checked unconditionally (same
    pattern as NEXT_DATA) and its strictly cheaper match overrides
    JSON-LD's cruder one."""
    rsc_scripts = _rsc_page(
        {
            "3c": {"itemNo": 3567244, "internalDisplayPrice": "$a7"},
            "a7": {"totalDiscountedItemPrice": 329800},
        }
    ).split("<body>", 1)[1]
    html = (
        '<html><head><script type="application/ld+json">'
        + json.dumps({"@type": "Product", "offers": {"price": "388000"}})
        + "</script></head><body>"
        + rsc_scripts
    )
    result = await s._run_hierarchy(html, "https://www.29cm.co.kr/products/3567244")
    # currency="KRW", not the other tests' "CAD" default — .co.kr triggers
    # the existing TLD-based KRW fallback (_extract_currency), unrelated
    # to this test's actual subject (the price override).
    assert result == ScraperResult(price=329800.0, status="ok", currency="KRW")


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
    assert result == ScraperResult(price=89.99, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_http_scraper_connection_error_returns_error() -> None:
    respx.get("http://localhost:9999/nope").mock(side_effect=httpx.ConnectError("refused"))
    result = await HTTPScraper().get_price("http://localhost:9999/nope")
    assert result == ScraperResult(price=None, status="error", error_reason="ConnectError: refused")


# ---------------------------------------------------------------------------
# _split_title / _first_title_segment / _last_title_segment (issue #44)
# ---------------------------------------------------------------------------

def test_split_title_dash_separator() -> None:
    assert _split_title("Cayl Cap Black - Muddy George") == ("Cayl Cap Black", "Muddy George")


def test_split_title_pipe_separator() -> None:
    assert _split_title("Cayl Cap Black | Muddy George") == ("Cayl Cap Black", "Muddy George")


def test_split_title_en_dash_separator() -> None:
    assert _split_title("Cayl Cap Black – Muddy George") == ("Cayl Cap Black", "Muddy George")


def test_split_title_no_separator_returns_none() -> None:
    assert _split_title("Cayl Cap Black") is None


def test_split_title_ambiguous_multiple_separator_types_returns_none() -> None:
    # Both "-" and "|" appear — too ambiguous to guess which one is the
    # real product/site boundary.
    assert _split_title("Cayl Cap - Black | Muddy George") is None


def test_split_title_empty_segment_returns_none() -> None:
    assert _split_title("- Muddy George") is None
    assert _split_title("Cayl Cap Black -") is None


def test_first_and_last_title_segment() -> None:
    title = "Cayl Cap Black - Muddy George"
    assert _first_title_segment(title) == "Cayl Cap Black"
    assert _last_title_segment(title) == "Muddy George"


def test_first_and_last_title_segment_no_separator_return_none() -> None:
    assert _first_title_segment("Cayl Cap Black") is None
    assert _last_title_segment("Cayl Cap Black") is None


# ---------------------------------------------------------------------------
# _extract_site_name (issue #44)
# ---------------------------------------------------------------------------

def test_extract_site_name_og_tag() -> None:
    html = '<html><head><meta property="og:site_name" content="Muddy George"></head></html>'
    assert _extract_site_name(_soup(html)) == "Muddy George"


def test_extract_site_name_jsonld_organization() -> None:
    html = _jsonld_page({"@type": "Organization", "name": "Muddy George"})
    assert _extract_site_name(_soup(html)) == "Muddy George"


def test_extract_site_name_jsonld_brand() -> None:
    html = _jsonld_page({"@type": "Brand", "name": "Muddy George"})
    assert _extract_site_name(_soup(html)) == "Muddy George"


def test_extract_site_name_title_fallback() -> None:
    html = "<html><head><title>Cayl Cap Black - Muddy George</title></head></html>"
    assert _extract_site_name(_soup(html)) == "Muddy George"


def test_extract_site_name_og_tag_wins_over_jsonld() -> None:
    html = (
        '<html><head><meta property="og:site_name" content="Muddy George">'
        '<script type="application/ld+json">{"@type": "Organization", "name": "Wrong Name"}</script>'
        "</head></html>"
    )
    assert _extract_site_name(_soup(html)) == "Muddy George"


def test_extract_site_name_no_signal_returns_none() -> None:
    assert _extract_site_name(_soup("<html><body>nothing</body></html>")) is None


def test_extract_site_name_ambiguous_title_returns_none() -> None:
    html = "<html><head><title>No separator here</title></head></html>"
    assert _extract_site_name(_soup(html)) is None


# ---------------------------------------------------------------------------
# _extract_product_title (issue #44)
# ---------------------------------------------------------------------------

def test_extract_product_title_og_tag() -> None:
    html = '<html><head><meta property="og:title" content="Cayl Cap Black"></head></html>'
    assert _extract_product_title(_soup(html)) == "Cayl Cap Black"


def test_extract_product_title_jsonld_product() -> None:
    html = _jsonld_page({"@type": "Product", "name": "Cayl Cap Black"})
    assert _extract_product_title(_soup(html)) == "Cayl Cap Black"


def test_extract_product_title_title_fallback() -> None:
    html = "<html><head><title>Cayl Cap Black - Muddy George</title></head></html>"
    assert _extract_product_title(_soup(html)) == "Cayl Cap Black"


def test_extract_product_title_no_signal_returns_none() -> None:
    assert _extract_product_title(_soup("<html><body>nothing</body></html>")) is None


# ---------------------------------------------------------------------------
# _extract_currency (issue #45)
# ---------------------------------------------------------------------------

def test_extract_currency_og_price_currency_meta() -> None:
    html = '<html><head><meta property="og:price:currency" content="USD"></head></html>'
    assert _extract_currency(_soup(html), "https://example.com/item") == "USD"


def test_extract_currency_jsonld_price_currency() -> None:
    html = _jsonld_page({"@type": "Product", "offers": {"price": "52.00", "priceCurrency": "KRW"}})
    assert _extract_currency(_soup(html), "https://example.com/item") == "KRW"


def test_extract_currency_unsupported_jsonld_code_falls_through_to_default() -> None:
    html = _jsonld_page({"@type": "Product", "offers": {"price": "52.00", "priceCurrency": "EUR"}})
    assert _extract_currency(_soup(html), "https://example.com/item") == "CAD"


def test_extract_currency_won_symbol() -> None:
    html = "<html><body>Price: ₩52,000</body></html>"
    assert _extract_currency(_soup(html), "https://example.com/item") == "KRW"


def test_extract_currency_won_word() -> None:
    html = "<html><body>가격: 52,000원</body></html>"
    assert _extract_currency(_soup(html), "https://example.com/item") == "KRW"


def test_extract_currency_us_dollar_marker() -> None:
    html = "<html><body>Price: US$52.00</body></html>"
    assert _extract_currency(_soup(html), "https://example.com/item") == "USD"


def test_extract_currency_kr_tld_with_no_page_signal() -> None:
    # The real goyowear.kr case: no priceCurrency, no symbol, just a bare
    # number — TLD is the only signal left.
    html = "<html><body>388000</body></html>"
    assert _extract_currency(_soup(html), "https://goyowear.kr/product/endure-jacket") == "KRW"


def test_extract_currency_bare_dollar_defaults_to_cad_regardless_of_tld() -> None:
    # muddygeorge.com is a real Canadian retailer on a plain .com domain —
    # TLD must NOT push this to USD.
    html = "<html><body>Price: $52.00</body></html>"
    assert _extract_currency(_soup(html), "https://muddygeorge.com/products/cayl-cap") == "CAD"


def test_extract_currency_no_signal_at_all_defaults_to_cad() -> None:
    html = "<html><body>nothing</body></html>"
    assert _extract_currency(_soup(html), "https://example.com/product") == "CAD"


def test_extract_currency_metadata_wins_over_kr_tld() -> None:
    html = '<html><head><meta property="og:price:currency" content="USD"></head></html>'
    assert _extract_currency(_soup(html), "https://example.kr/product") == "USD"


# Issue #63 — Shopify's declared storefront currency.

def test_extract_currency_dickies_shopify_cad_beats_jsonld_usd() -> None:
    # Trimmed from the real dickies.com/en-ca page: the Product JSON-LD
    # carries the shop's base currency (USD) and a hidden microdata span says
    # USD too, but Shopify's own scripts say the storefront presents CAD.
    html = textwrap.dedent(
        """
        <html><head>
        <script type="application/ld+json">
        {"@context": "https://schema.org", "@type": "Product", "name": "Carpenter Pants",
         "offers": {"@type": "Offer", "price": "61.0", "priceCurrency": "USD"}}
        </script>
        <script>
          var Shopify = Shopify || {};
          Shopify.currency = {"active":"CAD","rate":"1.4406707"};
        </script>
        </head><body>
        <span class="price">61.00</span><span class="price_currency_code">USD</span>
        </body></html>
        """
    )
    assert _extract_currency(_soup(html), "https://www.dickies.com/en-ca/products/pants") == "CAD"


def test_extract_currency_shopify_analytics_meta_currency() -> None:
    html = textwrap.dedent(
        """
        <html><head><script>
          window.ShopifyAnalytics = window.ShopifyAnalytics || {};
          window.ShopifyAnalytics.meta = window.ShopifyAnalytics.meta || {};
          window.ShopifyAnalytics.meta.currency = 'USD';
        </script></head><body>Price: $52.00</body></html>
        """
    )
    assert _extract_currency(_soup(html), "https://example.com/products/x") == "USD"


def test_extract_currency_shopify_unsupported_currency_falls_through() -> None:
    html = textwrap.dedent(
        """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "offers": {"price": "52.00", "priceCurrency": "KRW"}}
        </script>
        <script>Shopify.currency = {"active":"EUR","rate":"0.65"};</script>
        </head></html>
        """
    )
    assert _extract_currency(_soup(html), "https://example.com/products/x") == "KRW"


def test_extract_currency_non_shopify_script_mentioning_currency_is_ignored() -> None:
    html = '<html><head><script>var cfg = {"currency": "USD"};</script></head><body>Price: $52.00</body></html>'
    assert _extract_currency(_soup(html), "https://muddygeorge.com/products/cayl-cap") == "CAD"


@pytest.mark.parametrize(
    "chrome",
    [
        '<select><option value="CAD">CAD</option><option value="USD">USD</option></select>',
        "<footer>Orders to the US ship from US$ warehouses</footer>",
        "<nav><a>Shop in USD</a></nav>",
    ],
)
def test_extract_currency_ignores_usd_in_page_chrome(chrome: str) -> None:
    html = f"<html><body>{chrome}<div>Price: $52.00</div></body></html>"
    assert _detect_currency(_soup(html), "https://example.ca/p/1") == ("CAD", "default")


def test_extract_currency_usd_in_product_area_still_detected() -> None:
    html = "<html><body><footer>Contact us</footer><div>Price: US$52.00</div></body></html>"
    assert _detect_currency(_soup(html), "https://example.com/p/1") == ("USD", "text_scan")


def test_extract_currency_ignores_usd_in_script_text() -> None:
    html = '<html><body><script>var label = "USD";</script><div>Price: $52.00</div></body></html>'
    assert _detect_currency(_soup(html), "https://example.com/p/1") == ("CAD", "default")


@pytest.mark.parametrize(
    "html, url, expected",
    [
        ('<html><head><meta property="og:price:currency" content="USD"></head></html>', "https://x.com/p", ("USD", "meta")),
        ("<html><body>₩29,000</body></html>", "https://x.com/p", ("KRW", "text_scan")),
        ("<html><body>29,000</body></html>", "https://x.kr/p", ("KRW", "tld")),
    ],
)
def test_detect_currency_reports_deciding_signal(html: str, url: str, expected: tuple[str, str]) -> None:
    assert _detect_currency(_soup(html), url) == expected


# ---------------------------------------------------------------------------
# _run_hierarchy attaches site_name/product_title independently of which
# price method wins (issue #44)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_hierarchy_attaches_name_metadata_alongside_jsonld_price() -> None:
    html = (
        '<html><head><meta property="og:site_name" content="Muddy George">'
        '<meta property="og:title" content="Cayl Cap Black">'
        '<script type="application/ld+json">{"@type": "Product", "offers": {"price": "52.00"}}</script>'
        "</head></html>"
    )
    s = DummyScraper()
    result = await s._run_hierarchy(html, "https://muddygeorge.com/products/cayl-cap")
    assert result == ScraperResult(price=52.0, status="ok", site_name="Muddy George", product_title="Cayl Cap Black", currency="CAD")


@pytest.mark.asyncio
async def test_run_hierarchy_no_name_metadata_found_leaves_fields_none() -> None:
    html = _jsonld_page({"@type": "Product", "offers": {"price": "89.99"}})
    s = DummyScraper()
    result = await s._run_hierarchy(html, "https://example.com/product")
    assert result.site_name is None
    assert result.product_title is None


# ---------------------------------------------------------------------------
# _strip_trailing_site_name (issue #44 follow-up — og:title often carries
# its own trailing "- Site Name" suffix, e.g. goyowear.kr's real page:
# og:title="ENDURE GOOSE DOWN JACKET (DARK GREY) - GOYOWEAR",
# og:site_name="GOYOWEAR")
# ---------------------------------------------------------------------------

def test_strip_trailing_site_name_matching_suffix_removed() -> None:
    assert _strip_trailing_site_name("Endure Jacket - GOYOWEAR", "GOYOWEAR") == "Endure Jacket"


def test_strip_trailing_site_name_case_insensitive() -> None:
    assert _strip_trailing_site_name("Endure Jacket - goyowear", "GOYOWEAR") == "Endure Jacket"


def test_strip_trailing_site_name_no_site_name_is_noop() -> None:
    assert _strip_trailing_site_name("Endure Jacket - GOYOWEAR", None) == "Endure Jacket - GOYOWEAR"


def test_strip_trailing_site_name_non_matching_tail_is_noop() -> None:
    # The dash here is part of the real product name, not a site-name
    # suffix — since the tail doesn't match the known site_name, must not
    # get truncated on a blind guess.
    assert _strip_trailing_site_name("Air Force 1 - Low", "Nike") == "Air Force 1 - Low"


def test_strip_trailing_site_name_no_separator_is_noop() -> None:
    assert _strip_trailing_site_name("Endure Jacket", "GOYOWEAR") == "Endure Jacket"


@pytest.mark.asyncio
async def test_run_hierarchy_strips_matching_site_name_from_og_title() -> None:
    """The actual goyowear.kr regression — og:title carries a trailing
    "- GOYOWEAR" that matches og:site_name, so the saved product_title
    should be the clean product-only name, not the raw og:title."""
    html = (
        '<html><head><meta property="og:site_name" content="GOYOWEAR">'
        '<meta property="og:title" content="Endure Goose Down Jacket - GOYOWEAR">'
        '<script type="application/ld+json">{"@type": "Product", "offers": {"price": "388000"}}</script>'
        "</head></html>"
    )
    s = DummyScraper()
    result = await s._run_hierarchy(html, "https://goyowear.kr/product/endure-jacket")
    assert result.site_name == "GOYOWEAR"
    assert result.product_title == "Endure Goose Down Jacket"
