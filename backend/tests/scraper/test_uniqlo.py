"""Tests for UniqloScraper (issue #58) — Uniqlo's product page is a
client-rendered SPA with nothing for the generic extractors to read, so price
and per-variant stock come from its commerce API. Response shape below is
trimmed from two real captures (2026-10-11): E491096-000 (variant 67/004 in
stock, quantity 11, $79.90, no promo) and E488599-000 (variant 38/003
STOCK_OUT, quantity 0, $59.90)."""

import httpx
import pytest
import respx

from app.services.scraper.config import UNIQLO_CLIENT_IDS
from app.services.scraper.result import ScraperResult
from app.services.scraper.router import RETAILER_MAP, _derive_retailer
from app.services.scraper.uniqlo_scraper import UniqloScraper

API_BASE = "https://www.uniqlo.com/ca/api/commerce/v5/en/products/E491096-000/price-groups/00/l2s"
LOOKUP_BASE = "https://www.uniqlo.com/ca/api/commerce/v5/en/products?"
IN_STOCK_URL = "https://www.uniqlo.com/ca/en/products/E491096-000/00?colorDisplayCode=67&sizeDisplayCode=004"


def _variant(
    color: str,
    size: str,
    l2_id: str,
    *,
    quantity: int = 11,
    status: str = "IN_STOCK",
    base: float = 79.9,
    promo: float | None = None,
    currency: str = "CAD",
) -> dict:
    """One (l2, stock, price) triple in the API's real shape."""
    cur = {"code": currency, "symbol": "$"}
    return {
        "l2": {
            "color": {"code": f"COL{color}", "displayCode": color},
            "size": {"code": f"SMA{size}", "displayCode": size},
            "l2Id": l2_id,
        },
        "stock": {"statusCode": status, "quantity": quantity, "backInStock": status == "STOCK_OUT"},
        "price": {
            "base": {"currency": cur, "value": base},
            "promo": {"currency": cur, "value": promo} if promo is not None else None,
            "taxPolicy": "EXCLUSIVE",
        },
    }


def _api(*variants: dict) -> dict:
    return {
        "status": "ok",
        "result": {
            "l2s": [v["l2"] for v in variants],
            "stocks": {v["l2"]["l2Id"]: v["stock"] for v in variants},
            "prices": {v["l2"]["l2Id"]: v["price"] for v in variants},
        },
    }


def _mock(payload: dict, status: int = 200):
    return respx.get(url__startswith=API_BASE).mock(return_value=httpx.Response(status, json=payload))


def _lookup_payload(name: str = "Zip Up Blouson") -> dict:
    """Trimmed from the real `products?productIds=E491096-000` response."""
    return {
        "status": "ok",
        "result": {
            "items": [
                {
                    "productId": "E491096-000",
                    "name": name,
                    "colors": [{"displayCode": "34", "name": "BROWN"}, {"displayCode": "67", "name": "BLUE"}],
                    "sizes": [{"displayCode": "003", "name": "S"}, {"displayCode": "004", "name": "M"}],
                }
            ]
        },
    }


def _mock_lookup(payload: dict | None = None, status: int = 200):
    return respx.get(url__startswith=LOOKUP_BASE).mock(
        return_value=httpx.Response(status, json=payload if payload is not None else _lookup_payload())
    )


# ── routing ──────────────────────────────────────────────────────────────


def test_uniqlo_is_routed_to_the_dedicated_scraper() -> None:
    assert RETAILER_MAP["uniqlo.com"] is UniqloScraper
    assert _derive_retailer("uniqlo.com") == "Uniqlo"


# ── exact variant ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_exact_variant_in_stock_returns_ok_with_price_and_currency() -> None:
    route = _mock(_api(_variant("67", "004", "A1"), _variant("67", "005", "A2", quantity=0, status="STOCK_OUT")))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(price=79.9, status="ok", currency="CAD")
    request = route.calls.last.request
    assert request.headers["x-fr-clientid"] == UNIQLO_CLIENT_IDS["ca"]
    assert request.url.params["withStocks"] == "true"
    assert request.url.params["withPrices"] == "true"


@pytest.mark.asyncio
@respx.mock
async def test_exact_variant_sold_out_is_oos_with_price_kept_even_if_others_in_stock() -> None:
    _mock(
        _api(
            _variant("67", "004", "A1", quantity=0, status="STOCK_OUT", base=59.9),
            _variant("67", "005", "A2"),
        )
    )

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(price=59.9, status="oos", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_promo_price_wins_over_base() -> None:
    _mock(_api(_variant("67", "004", "A1", base=79.9, promo=59.9)))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.price == 59.9


@pytest.mark.asyncio
@respx.mock
async def test_quantity_zero_is_oos_even_with_in_stock_status() -> None:
    _mock(_api(_variant("67", "004", "A1", quantity=0, status="IN_STOCK")))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "oos"


@pytest.mark.asyncio
@respx.mock
async def test_low_quantity_in_stock_is_ok() -> None:
    _mock(_api(_variant("67", "004", "A1", quantity=4)))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "ok"


# ── no color / size ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_no_variant_skips_sold_out_first_and_prices_first_in_stock() -> None:
    _mock(
        _api(
            _variant("34", "002", "A1", quantity=0, status="STOCK_OUT", base=70.0),
            _variant("34", "003", "A2", base=79.9),
            _variant("67", "004", "A3", base=89.9),
        )
    )

    result = await UniqloScraper().get_price("https://www.uniqlo.com/ca/en/products/E491096-000/00")

    assert result == ScraperResult(price=79.9, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_no_variant_all_sold_out_is_oos() -> None:
    _mock(
        _api(
            _variant("34", "002", "A1", quantity=0, status="STOCK_OUT"),
            _variant("67", "004", "A2", quantity=0, status="STOCK_OUT"),
        )
    )

    result = await UniqloScraper().get_price("https://www.uniqlo.com/ca/en/products/E491096-000/00")

    assert result.status == "oos"
    assert result.price == 79.9


@pytest.mark.asyncio
@respx.mock
async def test_color_only_is_restricted_to_that_color() -> None:
    _mock(
        _api(
            _variant("34", "003", "A1", base=70.0),
            _variant("67", "004", "A2", quantity=0, status="STOCK_OUT", base=89.9),
        )
    )

    result = await UniqloScraper().get_price(
        "https://www.uniqlo.com/ca/en/products/E491096-000/00?colorDisplayCode=67"
    )

    assert result == ScraperResult(price=89.9, status="oos", currency="CAD")


# ── URL handling ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_missing_price_group_defaults_to_00() -> None:
    route = _mock(_api(_variant("67", "004", "A1")))

    result = await UniqloScraper().get_price(
        "https://www.uniqlo.com/ca/en/products/E491096-000?colorDisplayCode=67&sizeDisplayCode=004"
    )

    assert result.status == "ok"
    assert "/price-groups/00/l2s" in str(route.calls.last.request.url)


@pytest.mark.asyncio
@respx.mock
async def test_french_language_is_taken_from_the_url() -> None:
    route = respx.get(url__startswith=API_BASE.replace("/en/", "/fr/")).mock(
        return_value=httpx.Response(200, json=_api(_variant("67", "004", "A1")))
    )

    result = await UniqloScraper().get_price(
        "https://www.uniqlo.com/ca/fr/products/E491096-000/00?colorDisplayCode=67&sizeDisplayCode=004"
    )

    assert result.status == "ok"
    assert route.called


@pytest.mark.asyncio
async def test_unsupported_region_errors_without_a_request() -> None:
    result = await UniqloScraper().get_price("https://www.uniqlo.com/us/en/products/E491096-000/00")

    assert result == ScraperResult(price=None, status="error", error_reason="unsupported Uniqlo region 'us'")


@pytest.mark.asyncio
async def test_url_without_product_id_errors() -> None:
    result = await UniqloScraper().get_price("https://www.uniqlo.com/ca/en/women/")

    assert result == ScraperResult(price=None, status="error", error_reason="no Uniqlo product ID found in URL")


# ── failures carry specific reasons ──────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_variant_not_found_errors_naming_the_variant() -> None:
    _mock(_api(_variant("34", "003", "A1")))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(
        price=None, status="error", error_reason="variant color=67, size=004 not found for E491096-000"
    )


@pytest.mark.asyncio
@respx.mock
async def test_api_error_message_is_surfaced() -> None:
    body = {"status": "nok", "error": {"code": 0, "details": [{"message": "invalid or missing client id"}]}}
    _mock(body, status=400)

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(
        price=None, status="error", error_reason="Uniqlo API HTTP 400: invalid or missing client id"
    )


@pytest.mark.asyncio
@respx.mock
async def test_non_json_http_error_still_has_a_reason() -> None:
    respx.get(url__startswith=API_BASE).mock(return_value=httpx.Response(403, text="Access Denied"))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "error"
    assert result.error_reason == "Uniqlo API HTTP 403: no details"


@pytest.mark.asyncio
@respx.mock
async def test_unexpected_response_shape_errors() -> None:
    _mock({"status": "ok", "result": {"l2s": "nope"}})

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(price=None, status="error", error_reason="unexpected Uniqlo API response shape")


@pytest.mark.asyncio
@respx.mock
async def test_variant_without_stock_or_price_data_errors() -> None:
    payload = _api(_variant("67", "004", "A1"))
    del payload["result"]["stocks"]["A1"]
    _mock(payload)

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "error"
    assert "no stock or price data for variant A1" in result.error_reason


@pytest.mark.asyncio
@respx.mock
async def test_network_exception_errors() -> None:
    respx.get(url__startswith=API_BASE).mock(side_effect=httpx.ConnectError("boom"))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "error"
    assert result.error_reason.startswith("ConnectError")


@pytest.mark.asyncio
@respx.mock
async def test_unsupported_currency_is_none() -> None:
    _mock(_api(_variant("67", "004", "A1", currency="EUR")))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.currency is None
    assert result.status == "ok"


# ── item name (#44 inference) ────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_title_includes_the_tracked_color_and_size() -> None:
    _mock(_api(_variant("67", "004", "A1")))
    route = _mock_lookup()

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(
        price=79.9, status="ok", currency="CAD", product_title="Zip Up Blouson (BLUE, M)"
    )
    request = route.calls.last.request
    assert request.url.params["productIds"] == "E491096-000"
    assert request.headers["x-fr-clientid"] == UNIQLO_CLIENT_IDS["ca"]


@pytest.mark.asyncio
@respx.mock
async def test_title_is_set_on_oos_results_too() -> None:
    _mock(_api(_variant("67", "004", "A1", quantity=0, status="STOCK_OUT")))
    _mock_lookup()

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "oos"
    assert result.product_title == "Zip Up Blouson (BLUE, M)"


@pytest.mark.asyncio
@respx.mock
async def test_title_color_only_and_plain() -> None:
    _mock(_api(_variant("67", "004", "A1")))
    _mock_lookup()

    color_only = await UniqloScraper().get_price(
        "https://www.uniqlo.com/ca/en/products/E491096-000/00?colorDisplayCode=67"
    )
    plain = await UniqloScraper().get_price("https://www.uniqlo.com/ca/en/products/E491096-000/00")

    assert color_only.product_title == "Zip Up Blouson (BLUE)"
    assert plain.product_title == "Zip Up Blouson"


@pytest.mark.asyncio
@respx.mock
async def test_failed_name_lookup_does_not_fail_the_scrape() -> None:
    _mock(_api(_variant("67", "004", "A1")))
    _mock_lookup(status=500)

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result == ScraperResult(price=79.9, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_name_lookup_exception_does_not_fail_the_scrape() -> None:
    _mock(_api(_variant("67", "004", "A1")))
    respx.get(url__startswith=LOOKUP_BASE).mock(side_effect=httpx.ConnectError("boom"))

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.status == "ok"
    assert result.product_title is None


@pytest.mark.asyncio
@respx.mock
async def test_lookup_for_a_different_product_is_ignored() -> None:
    _mock(_api(_variant("67", "004", "A1")))
    payload = _lookup_payload()
    payload["result"]["items"][0]["productId"] = "E000000-000"
    _mock_lookup(payload)

    result = await UniqloScraper().get_price(IN_STOCK_URL)

    assert result.product_title is None
