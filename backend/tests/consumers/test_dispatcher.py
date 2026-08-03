from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.consumers import dispatcher


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _closing_spawn(coro):
    """Stand-in for trading_agents.spawn() — closes the coroutine instead of
    scheduling it, so tests never trigger a real subprocess/DB call and never
    leak a "coroutine was never awaited" warning."""
    coro.close()
    return MagicMock()


@pytest.mark.asyncio
async def test_dispatch_price_drop_marks_processed() -> None:
    event = SimpleNamespace(
        id=1,
        type="PRICE_DROP",
        payload={
            "product_id": 11,
            "listing_id": 22,
            "retailer": "amazon_ca",
            "price": 89.99,
            "url": "https://example.com/item",
        },
        status="pending",
        processed_at=None,
    )
    product = SimpleNamespace(id=11, name="Shoes", target_price=100.0)

    notify_session = MagicMock()

    async def _notify_get(model, row_id):
        if model.__name__ == "Event":
            return event
        if model.__name__ == "Product":
            return product
        return None

    notify_session.get = AsyncMock(side_effect=_notify_get)
    notify_session.commit = AsyncMock()

    status_event = SimpleNamespace(status="pending", processed_at=None)
    status_session = MagicMock()
    status_session.get = AsyncMock(return_value=status_event)
    status_session.commit = AsyncMock()

    with (
        patch(
            "app.consumers.dispatcher.AsyncSessionLocal",
            side_effect=[_AsyncCM(notify_session), _AsyncCM(status_session)],
        ),
        patch("app.consumers.notify.send_alert", new=AsyncMock()) as send_alert,
    ):
        await dispatcher._dispatch(1)

    send_alert.assert_awaited_once_with(
        "Price Drop: Shoes",
        "Now $89.99 at amazon_ca (target $100.00)",
        "https://example.com/item",
        0,
    )
    status_session.commit.assert_awaited_once()
    assert status_event.status == "processed"
    assert status_event.processed_at is not None


@pytest.mark.asyncio
async def test_dispatch_stock_threshold_creates_analysis_result_and_marks_processed() -> None:
    event = SimpleNamespace(
        id=2,
        type="STOCK_THRESHOLD",
        payload={
            "alert_id": 22,
            "ticker": "AAPL",
            "price": 190.5,
            "target_price": 180.0,
            "direction": "above",
        },
        status="pending",
        processed_at=None,
    )

    notify_session = MagicMock()
    notify_session.get = AsyncMock(return_value=event)
    notify_session.commit = AsyncMock()

    analysis_session = MagicMock()
    analysis_session.get = AsyncMock(return_value=SimpleNamespace(id=22, run_analysis=True))
    analysis_session.commit = AsyncMock()
    analysis_session.add = MagicMock()

    status_event = SimpleNamespace(status="pending", processed_at=None)
    status_session = MagicMock()
    status_session.get = AsyncMock(return_value=status_event)
    status_session.commit = AsyncMock()

    with (
        patch(
            "app.consumers.dispatcher.AsyncSessionLocal",
            side_effect=[
                _AsyncCM(notify_session),
                _AsyncCM(analysis_session),
                _AsyncCM(status_session),
            ],
        ),
        patch("app.consumers.notify.send_alert", new=AsyncMock()) as send_alert,
        patch("app.services.trading_agents.spawn", side_effect=_closing_spawn) as spawn,
    ):
        await dispatcher._dispatch(2)

    spawn.assert_called_once()

    send_alert.assert_awaited_once_with(
        "Stock Alert: AAPL above $180.00",
        "Now $190.5000 (target $180.00 above)",
        None,
        0,
    )
    analysis_session.add.assert_called_once()
    analysis_result = analysis_session.add.call_args.args[0]
    assert analysis_result.stock_alert_id == 22
    assert analysis_result.event_id == 2
    assert analysis_result.ticker == "AAPL"
    assert analysis_result.triggered_price == 190.5
    assert analysis_result.status == "pending"
    # handle() commits for real (must be durable before spawn() hands the row to a
    # background task on a separate connection); dispatcher._dispatch's own commit
    # after handle() returns is then a harmless no-op on top — hence 2, not 1.
    assert analysis_session.commit.await_count == 2

    status_session.commit.assert_awaited_once()
    assert status_event.status == "processed"
    assert status_event.processed_at is not None


@pytest.mark.asyncio
async def test_dispatch_missing_product_marks_failed() -> None:
    event = SimpleNamespace(
        id=3,
        type="PRICE_DROP",
        payload={
            "product_id": 999,
            "listing_id": 1,
            "retailer": "amazon_ca",
            "price": 70.0,
            "url": "https://example.com/missing",
        },
        status="pending",
        processed_at=None,
    )

    session = MagicMock()

    async def _get(model, row_id):
        if model.__name__ == "Event":
            return event
        if model.__name__ == "Product":
            return None
        return None

    session.get = AsyncMock(side_effect=_get)
    session.commit = AsyncMock()

    with (
        patch("app.consumers.dispatcher.AsyncSessionLocal", return_value=_AsyncCM(session)) as session_local,
        patch("app.consumers.notify.send_alert", new=AsyncMock()) as send_alert,
    ):
        await dispatcher._dispatch(3)

    send_alert.assert_not_awaited()
    session.commit.assert_awaited_once()
    assert event.status == "failed"
    assert event.processed_at is None
    assert session_local.call_count == 1
