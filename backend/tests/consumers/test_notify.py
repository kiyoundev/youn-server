from types import SimpleNamespace

import pytest

from app.consumers import notify


def _threshold_event(**payload_overrides) -> SimpleNamespace:
    payload = {
        "alert_id": 1,
        "ticker": "AAPL",
        "price": 65.0,
        "target_price": 70.0,
        "direction": "below",
    }
    payload.update(payload_overrides)
    return SimpleNamespace(id=1, type="STOCK_THRESHOLD", payload=payload)


def test_format_stock_threshold_buy_signal_default_when_alert_type_missing():
    """Events fired before alert_type existed have no key in payload — must
    default to buy_signal, not crash or silently be treated as stop_loss."""
    title, body, url, priority = notify._format_stock_threshold(_threshold_event())

    assert title == "Stock Alert: AAPL below $70.00"
    assert "65.0000" in body
    assert url is None
    assert priority == notify._PRIORITY_NORMAL


def test_format_stock_threshold_buy_signal_explicit():
    event = _threshold_event(alert_type="buy_signal")
    title, body, url, priority = notify._format_stock_threshold(event)

    assert title == "Stock Alert: AAPL below $70.00"
    assert priority == notify._PRIORITY_NORMAL


def test_format_stock_threshold_stop_loss_distinct_message_and_priority():
    event = _threshold_event(alert_type="stop_loss")
    title, body, url, priority = notify._format_stock_threshold(event)

    assert title == "STOP-LOSS: SELL AAPL NOW"
    assert "sell as soon as possible" in body.lower()
    assert priority == notify._PRIORITY_HIGH
    assert priority > notify._PRIORITY_NORMAL


def test_format_stock_threshold_take_profit_distinct_message_normal_priority():
    event = _threshold_event(alert_type="take_profit", direction="above", target_price=150.0)
    title, body, url, priority = notify._format_stock_threshold(event)

    assert title == "Take Profit: AAPL hit $150.00"
    assert "lock in gains" in body.lower()
    assert priority == notify._PRIORITY_NORMAL


@pytest.mark.asyncio
async def test_format_price_drop_uses_normal_priority():
    session = SimpleNamespace()

    async def _get(model, row_id):
        return SimpleNamespace(id=row_id, name="Shoes", target_price=100.0)

    session.get = _get
    event = SimpleNamespace(
        id=5,
        payload={
            "product_id": 11,
            "listing_id": 22,
            "retailer": "amazon_ca",
            "price": 89.99,
            "url": "https://example.com/item",
        },
    )

    title, body, url, priority = await notify._format_price_drop(event, session)

    assert title == "Price Drop: Shoes"
    assert "amazon_ca" in body
    assert "89.99" in body
    assert "100.00" in body
    assert url == "https://example.com/item"
    assert priority == notify._PRIORITY_NORMAL


@pytest.mark.asyncio
async def test_format_price_drop_raises_when_product_not_found():
    session = SimpleNamespace()

    async def _get(model, row_id):
        return None

    session.get = _get
    event = SimpleNamespace(
        id=5,
        payload={"product_id": 11, "listing_id": 22, "retailer": "amazon_ca", "price": 89.99},
    )

    with pytest.raises(ValueError, match="Product 11 not found"):
        await notify._format_price_drop(event, session)
