import asyncio
import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from app.core.config import settings
from app.services.stocks import FinnhubClient, _AlertState


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_alert(
    alert_id: int,
    ticker: str,
    target_price: float = 100.0,
    direction: str = "below",
    alert_type: str = "buy_signal",
    alerted_at: dt.datetime | None = None,
):
    return SimpleNamespace(
        id=alert_id,
        ticker=ticker,
        target_price=target_price,
        direction=direction,
        alert_type=alert_type,
        alerted_at=alerted_at,
    )


@pytest.fixture
def client(monkeypatch) -> FinnhubClient:
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
    return FinnhubClient(asyncio.Queue())


def test_connected_property_reflects_ws_state(client: FinnhubClient) -> None:
    assert client.connected is False
    client._ws = SimpleNamespace(closed=False)
    assert client.connected is True
    client._ws = SimpleNamespace(closed=True)
    assert client.connected is False


@pytest.mark.asyncio
async def test_start_disabled_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "finnhub_api_key", "")
    c = FinnhubClient(asyncio.Queue())

    with patch("app.services.stocks.asyncio.create_task") as create_task:
        await c.start()

    create_task.assert_not_called()
    assert c._listener_task is None


@pytest.mark.asyncio
async def test_start_loads_active_alerts_and_starts_listener(client: FinnhubClient) -> None:
    alerts = [_make_alert(1, "AAPL"), _make_alert(2, "TSLA", direction="above")]
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = alerts
    result.scalars.return_value = scalars

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    fake_task = object()

    def _capture_and_close(coro):
        coro.close()
        return fake_task

    with (
        patch("app.services.stocks.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.services.stocks.asyncio.create_task", side_effect=_capture_and_close) as create_task,
    ):
        await client.start()

    assert create_task.call_count == 1
    assert client._listener_task is fake_task
    assert set(client._cache) == {"AAPL", "TSLA"}


@pytest.mark.asyncio
async def test_start_is_idempotent_when_listener_exists(client: FinnhubClient) -> None:
    client._listener_task = object()

    with patch("app.services.stocks.AsyncSessionLocal") as session_local:
        await client.start()

    session_local.assert_not_called()


@pytest.mark.asyncio
async def test_stop_cancels_listener_and_closes_ws(client: FinnhubClient) -> None:
    listener = asyncio.create_task(asyncio.sleep(3600))
    ws = AsyncMock()

    client._listener_task = listener
    client._ws = ws

    await client.stop()

    assert listener.cancelled() is True
    ws.close.assert_awaited_once()
    assert client._listener_task is None
    assert client._ws is None


def test_add_alert_new_ticker_schedules_subscribe(client: FinnhubClient) -> None:
    alert = _make_alert(1, "AAPL")
    scheduled = []

    def _drain(coro):
        scheduled.append(coro)
        coro.close()

    client._schedule = _drain

    client.add_alert(alert)

    assert len(client._cache["AAPL"]) == 1
    assert len(scheduled) == 1


def test_add_alert_duplicate_id_noop(client: FinnhubClient) -> None:
    alert = _make_alert(1, "AAPL")
    client._add_to_cache(alert)
    client._schedule = MagicMock()

    client.add_alert(alert)

    assert len(client._cache["AAPL"]) == 1
    client._schedule.assert_not_called()


def test_remove_alert_last_alert_schedules_unsubscribe(client: FinnhubClient) -> None:
    alert = _make_alert(1, "AAPL")
    client._add_to_cache(alert)
    scheduled = []

    def _drain(coro):
        scheduled.append(coro)
        coro.close()

    client._schedule = _drain

    client.remove_alert(1, "AAPL")

    assert "AAPL" not in client._cache
    assert len(scheduled) == 1


def test_remove_alert_keeps_ticker_when_others_remain(client: FinnhubClient) -> None:
    client._add_to_cache(_make_alert(1, "AAPL"))
    client._add_to_cache(_make_alert(2, "AAPL"))
    client._schedule = MagicMock()

    client.remove_alert(1, "AAPL")

    assert "AAPL" in client._cache
    assert [a.id for a in client._cache["AAPL"]] == [2]
    client._schedule.assert_not_called()


def test_update_alert_mutates_cached_state(client: FinnhubClient) -> None:
    client._add_to_cache(_make_alert(1, "AAPL", target_price=100.0, direction="below"))
    updated = _make_alert(1, "AAPL", target_price=150.0, direction="above", alerted_at=dt.datetime.now(dt.timezone.utc))

    client.update_alert(updated)

    state = client._cache["AAPL"][0]
    assert state.target_price == 150.0
    assert state.direction == "above"
    assert state.alerted_at == updated.alerted_at


def test_cached_tickers_returns_cache_keys(client: FinnhubClient) -> None:
    client._add_to_cache(_make_alert(1, "AAPL"))
    client._add_to_cache(_make_alert(2, "TSLA"))

    assert sorted(client.cached_tickers()) == ["AAPL", "TSLA"]


@pytest.mark.asyncio
async def test_check_threshold_public_delegates_to_private(client: FinnhubClient) -> None:
    client._check_threshold = AsyncMock()

    await client.check_threshold("AAPL", 123.45)

    client._check_threshold.assert_awaited_once_with("AAPL", 123.45)


@pytest.mark.asyncio
async def test_handle_message_ignores_invalid_json(client: FinnhubClient) -> None:
    client._check_threshold = AsyncMock()

    await client._handle_message("not-json")

    client._check_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_ignores_non_trade_messages(client: FinnhubClient) -> None:
    client._check_threshold = AsyncMock()

    await client._handle_message(json.dumps({"type": "ping"}))

    client._check_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_processes_trade_prices(client: FinnhubClient) -> None:
    client._check_threshold = AsyncMock()
    msg = {"type": "trade", "data": [{"s": "AAPL", "p": 123.45}]}

    await client._handle_message(json.dumps(msg))

    client._check_threshold.assert_awaited_once_with("AAPL", 123.45)


@pytest.mark.asyncio
async def test_handle_message_skips_trade_with_missing_fields(client: FinnhubClient) -> None:
    client._check_threshold = AsyncMock()
    msg = {"type": "trade", "data": [{"s": "AAPL"}, {"p": 10.0}]}

    await client._handle_message(json.dumps(msg))

    client._check_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_swallows_threshold_errors(client: FinnhubClient) -> None:
    client._check_threshold = AsyncMock(side_effect=RuntimeError("boom"))
    msg = {"type": "trade", "data": [{"s": "AAPL", "p": 5.0}]}

    await client._handle_message(json.dumps(msg))

    client._check_threshold.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_threshold_crossing_fires_once_and_blocks_duplicates(client: FinnhubClient) -> None:
    state = _AlertState(
        id=1, target_price=100.0, direction="below", alert_type="buy_signal", alerted_at=None
    )
    client._cache["AAPL"] = [state]
    client._fire_event = AsyncMock()

    await client._check_threshold("AAPL", 95.0)
    first_alerted = state.alerted_at
    await client._check_threshold("AAPL", 90.0)

    client._fire_event.assert_awaited_once()
    assert first_alerted is not None
    assert state.alerted_at == first_alerted


@pytest.mark.asyncio
async def test_check_threshold_recovery_clears_alerted_and_rearms(client: FinnhubClient) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    state = _AlertState(
        id=1, target_price=100.0, direction="below", alert_type="buy_signal", alerted_at=now
    )
    client._cache["AAPL"] = [state]
    client._clear_alerted_at = AsyncMock()

    await client._check_threshold("AAPL", 120.0)

    client._clear_alerted_at.assert_awaited_once_with(1)
    assert state.alerted_at is None


@pytest.mark.asyncio
async def test_check_threshold_noop_for_unknown_ticker(client: FinnhubClient) -> None:
    client._fire_event = AsyncMock()

    await client._check_threshold("MSFT", 200.0)

    client._fire_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_fire_event_persists_updates_and_enqueues(client: FinnhubClient) -> None:
    state = _AlertState(
        id=7, target_price=250.0, direction="above", alert_type="buy_signal", alerted_at=None
    )
    now = dt.datetime.now(dt.timezone.utc)
    alert_row = SimpleNamespace(last_price=None, alerted_at=None)

    def _assign_id(obj):
        obj.id = 42

    session = MagicMock()
    session.begin.return_value = _AsyncCM(None)
    session.get = AsyncMock(return_value=alert_row)
    session.add = MagicMock(side_effect=_assign_id)

    with patch("app.services.stocks.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await client._fire_event(state, "TSLA", 260.0, now)

    added_event = session.add.call_args[0][0]
    assert added_event.type == "STOCK_THRESHOLD"
    assert added_event.status == "pending"
    assert added_event.payload["ticker"] == "TSLA"
    assert added_event.payload["price"] == 260.0

    event_id = await client._queue.get()
    assert event_id == 42
    assert alert_row.last_price == 260.0
    assert alert_row.alerted_at == now


@pytest.mark.asyncio
async def test_clear_alerted_at_updates_row_if_found(client: FinnhubClient) -> None:
    alert_row = SimpleNamespace(alerted_at=dt.datetime.now(dt.timezone.utc))
    session = MagicMock()
    session.begin.return_value = _AsyncCM(None)
    session.get = AsyncMock(return_value=alert_row)

    with patch("app.services.stocks.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await client._clear_alerted_at(3)

    assert alert_row.alerted_at is None


@pytest.mark.asyncio
async def test_listen_reconnect_backoff_and_sleep(client: FinnhubClient) -> None:
    with (
        patch("app.services.stocks.websockets.connect", side_effect=[RuntimeError("down"), asyncio.CancelledError]),
        patch("app.services.stocks.asyncio.sleep", new=AsyncMock()) as sleep,
    ):
        with pytest.raises(asyncio.CancelledError):
            await client._listen()

    sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
@respx.mock
async def test_get_price_success(client: FinnhubClient) -> None:
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 321.09})
    )

    price = await client.get_price("AAPL")

    assert price == 321.09


@pytest.mark.asyncio
@respx.mock
async def test_get_price_sends_the_token_as_a_header_not_in_the_url(client: FinnhubClient) -> None:
    route = respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 321.09})
    )

    await client.get_price("AAPL")

    request = route.calls.last.request
    assert request.headers["X-Finnhub-Token"] == "test-key"
    assert "test-key" not in str(request.url)
    assert "token" not in request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_failed_quote_does_not_log_the_api_key(client: FinnhubClient, caplog) -> None:
    # raise_for_status puts the request URL in its message and the failure is
    # logged with exc_info, so a key in the URL would reach the logs
    respx.get("https://finnhub.io/api/v1/quote").mock(return_value=httpx.Response(429))

    with caplog.at_level("WARNING"):
        assert await client.get_price("AAPL") is None

    assert "Finnhub REST quote failed" in caplog.text  # the failure was logged
    assert "429" in caplog.text  # with the exception, so the URL leak path is exercised
    assert "test-key" not in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_get_price_returns_none_for_zero_or_missing(client: FinnhubClient) -> None:
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 0})
    )

    assert await client.get_price("AAPL") is None


@pytest.mark.asyncio
@respx.mock
async def test_get_price_returns_none_on_http_error(client: FinnhubClient) -> None:
    respx.get("https://finnhub.io/api/v1/quote").mock(return_value=httpx.Response(500))

    assert await client.get_price("AAPL") is None


@pytest.mark.asyncio
async def test_get_price_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "finnhub_api_key", "")
    c = FinnhubClient(asyncio.Queue())

    assert await c.get_price("AAPL") is None


@pytest.mark.asyncio
async def test_validate_ticker_true_false(client: FinnhubClient) -> None:
    client.get_price = AsyncMock(side_effect=[123.0, None])

    assert await client.validate_ticker("AAPL") is True
    assert await client.validate_ticker("INVALID_XYZ") is False


@pytest.mark.asyncio
async def test_get_price_history_success(client: FinnhubClient) -> None:
    class _Idx:
        def __init__(self, d: dt.date):
            self._d = d

        def date(self):
            return self._d

    class _History:
        def iterrows(self):
            yield _Idx(dt.date(2026, 1, 1)), {"Close": 101.5}
            yield _Idx(dt.date(2026, 1, 2)), {"Close": 102.25}

    fake_ticker = MagicMock()
    fake_ticker.history.return_value = _History()

    with patch("app.services.stocks.yf.Ticker", return_value=fake_ticker):
        result = await client.get_price_history("AAPL", "1mo")

    assert result == [
        {"date": "2026-01-01", "close": 101.5},
        {"date": "2026-01-02", "close": 102.25},
    ]


@pytest.mark.asyncio
async def test_get_price_history_returns_empty_on_error(client: FinnhubClient) -> None:
    with patch("app.services.stocks.yf.Ticker", side_effect=RuntimeError("down")):
        result = await client.get_price_history("AAPL", "1mo")

    assert result == []
