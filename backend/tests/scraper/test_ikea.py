"""Tests for IKEAScraper (issue #54) — dedicated per-store availability fix
for IKEA's product page always claiming JSON-LD "InStock" regardless of real
inventory."""

import json

import httpx
import pytest
import respx

from app.services.scraper.ikea_scraper import IKEAScraper
from app.services.scraper.result import ScraperResult

PRODUCT_URL = "https://www.ikea.com/ca/en/p/alpstuga-air-quality-sensor-smart-70609396/"
FRAGMENT_URL = (
    "https://www.ikea.com/ca/en/lower-funnel-fragments/"
    "product-availability/?itemNo=70609396&inline&storeId=256"
)


def _fragment_html(payload: dict) -> str:
    return f'<script type="text/hydrate">{json.dumps(payload)}</script>'


def _payload(
    *, price: float = 49.99, currency: str = "CAD", store: dict | None = None, availability_extra: dict | None = None
) -> dict:
    return {
        "product": {"itemNo": "70609396", "price": price, "currencyCode": currency},
        "availabilityResponse": {
            "availability": {
                "stores": {"256": store} if store is not None else {},
                **(availability_extra or {}),
            }
        },
    }


@pytest.mark.asyncio
@respx.mock
async def test_in_stock_returns_ok_with_price_and_currency() -> None:
    payload = _payload(store={"isOutOfStock": False, "stockStatus": "HIGH_IN_STOCK"})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(price=49.99, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_out_of_stock_returns_oos_with_price_and_restock_date_range() -> None:
    """IKEA shows price and availability as separate attributes — an OOS
    result keeps the real price, unlike the generic Shopify/JSON-LD OOS
    paths which have no price signal at all once out of stock."""
    payload = _payload(
        store={
            "isOutOfStock": True,
            "stockStatus": "OUT_OF_STOCK",
            "restocks": {"shortDate": ["Sep 22, 2026", "Sep 29, 2026"]},
        }
    )
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(
        price=49.99, status="oos", currency="CAD", restock_at="Sep 22, 2026–Sep 29, 2026"
    )


@pytest.mark.asyncio
@respx.mock
async def test_out_of_stock_with_no_restock_data_leaves_restock_at_none() -> None:
    payload = _payload(store={"isOutOfStock": True, "stockStatus": "OUT_OF_STOCK"})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(price=49.99, status="oos", currency="CAD", restock_at=None)


@pytest.mark.asyncio
@respx.mock
async def test_store_not_present_treated_as_in_stock() -> None:
    """Our store ID missing from the response entirely (e.g. IKEA drops it
    from the payload for some reason) degrades to "ok" rather than raising —
    matches the "store and store.get(...)" truthiness guard, not a KeyError."""
    payload = _payload(store=None)
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(price=49.99, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_unrecognized_currency_code_left_as_none() -> None:
    payload = _payload(currency="EUR", store={"isOutOfStock": False})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(price=49.99, status="ok", currency=None)


@pytest.mark.asyncio
@respx.mock
async def test_missing_hydrate_script_returns_error() -> None:
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text="<div>no data here</div>"))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(
        price=None, status="error", error_reason="availability data missing from IKEA response"
    )


@pytest.mark.asyncio
@respx.mock
async def test_malformed_json_in_hydrate_script_returns_error() -> None:
    respx.get(FRAGMENT_URL).mock(
        return_value=httpx.Response(200, text='<script type="text/hydrate">{not json</script>')
    )

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result.status == "error"
    assert result.error_reason.startswith("JSONDecodeError")


@pytest.mark.asyncio
@respx.mock
async def test_http_error_status_returns_error() -> None:
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(500))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result.status == "error"
    assert result.error_reason.startswith("HTTPStatusError")


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_returns_error() -> None:
    respx.get(FRAGMENT_URL).mock(side_effect=httpx.ConnectError("refused"))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result == ScraperResult(price=None, status="error", error_reason="ConnectError: refused")


@pytest.mark.asyncio
async def test_url_with_no_trailing_item_number_returns_error() -> None:
    result = await IKEAScraper().get_price("https://www.ikea.com/ca/en/p/some-page-with-no-id/")
    assert result == ScraperResult(price=None, status="error", error_reason="no item number found in URL")


@pytest.mark.asyncio
@respx.mock
async def test_trailing_query_string_does_not_break_item_number_extraction() -> None:
    """Regression for the Major finding from #54's review — a tracking query
    string (e.g. Google Shopping's real "?srsltid=...") after the item number
    must not prevent (or worse, corrupt) extraction, since the regex is
    anchored to end-of-string. Matching against the URL's path only, not the
    full URL, is what makes this safe."""
    payload = _payload(store={"isOutOfStock": False})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    url_with_tracking_param = PRODUCT_URL + "?srsltid=AfmBOopVlu7Sy3wzN3TBuvcSsZpWEgrQh1"
    result = await IKEAScraper().get_price(url_with_tracking_param)

    assert result == ScraperResult(price=49.99, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_numeric_query_param_does_not_get_mistaken_for_item_number() -> None:
    """A query string that itself ends in 6+ digits (e.g. a numeric variant
    id) must not be picked up as the item number instead of the real one in
    the path — this is exactly the silent-wrong-product risk the path-only
    match (vs. matching the raw URL) closes."""
    payload = _payload(store={"isOutOfStock": False})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    url_with_numeric_param = PRODUCT_URL + "?variant=99999999"
    result = await IKEAScraper().get_price(url_with_numeric_param)

    assert result == ScraperResult(price=49.99, status="ok", currency="CAD")


@pytest.mark.asyncio
@respx.mock
async def test_wrapped_loader_data_payload_is_unwrapped() -> None:
    """IKEA's hydration payload moved to {"0": {"loaderData": {...}}} — the
    old top-level lookup raised KeyError: 'product' for every item."""
    payload = {"0": {"loaderData": _payload(store={"isOutOfStock": False})}}
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result.status == "ok"
    assert result.price == 49.99


@pytest.mark.asyncio
@respx.mock
async def test_request_carries_configured_store_id(monkeypatch) -> None:
    """Without storeId IKEA returns an empty `stores` map, so OOS detection
    silently never ran. The id comes from settings, not a constant."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ikea_store_id", "123")
    payload = _payload(store=None)
    payload["availabilityResponse"]["availability"]["stores"] = {"123": {"isOutOfStock": True}}
    route = respx.get(
        "https://www.ikea.com/ca/en/lower-funnel-fragments/"
        "product-availability/?itemNo=70609396&inline&storeId=123"
    ).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert route.called
    assert result.status == "oos"


@pytest.mark.asyncio
@respx.mock
async def test_missing_store_falls_back_to_top_level_sold_out_flag() -> None:
    payload = _payload(store=None, availability_extra={"isSoldOut": True})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result.status == "oos"
    assert result.price == 49.99


@pytest.mark.asyncio
@respx.mock
async def test_missing_store_falls_back_to_home_delivery_out_of_stock() -> None:
    payload = _payload(store=None, availability_extra={"homeDelivery": {"isOutOfStock": True}})
    respx.get(FRAGMENT_URL).mock(return_value=httpx.Response(200, text=_fragment_html(payload)))

    result = await IKEAScraper().get_price(PRODUCT_URL)

    assert result.status == "oos"
