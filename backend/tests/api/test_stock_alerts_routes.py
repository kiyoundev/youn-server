from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api import stock_alerts
from app.schemas.stock_alert import StockAlertCreate, StockAlertUpdate


def _alert(
    alert_id: int = 1,
    *,
    ticker: str = "AAPL",
    target_price: float = 150.0,
    direction: str = "below",
    alert_type: str = "buy_signal",
    active: bool = True,
    run_analysis: bool = False,
    last_price: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=alert_id,
        ticker=ticker,
        target_price=target_price,
        direction=direction,
        alert_type=alert_type,
        active=active,
        run_analysis=run_analysis,
        last_price=last_price,
    )


def _request_with_finnhub(finnhub) -> SimpleNamespace:
    app = SimpleNamespace(state=SimpleNamespace(finnhub=finnhub))
    return SimpleNamespace(app=app)


def _closing_spawn(coro):
    """Stand-in for trading_agents.spawn() — closes the coroutine instead of
    scheduling it, so tests never trigger a real subprocess/DB call and never
    leak a "coroutine was never awaited" warning."""
    coro.close()
    return MagicMock()


@pytest.mark.asyncio
async def test_create_stock_alert_invalid_ticker_returns_400() -> None:
    db = MagicMock()
    finnhub = MagicMock()
    finnhub.validate_ticker = AsyncMock(return_value=False)
    request = _request_with_finnhub(finnhub)

    body = StockAlertCreate(ticker="INVALID_XYZ", target_price=100.0, direction="below")

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.create_stock_alert(body, request, db)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_stock_alert_valid_syncs_finnhub_cache() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    finnhub = MagicMock()
    finnhub.validate_ticker = AsyncMock(return_value=True)
    finnhub.add_alert = MagicMock()
    request = _request_with_finnhub(finnhub)

    body = StockAlertCreate(ticker="AAPL", target_price=150.0, direction="below")

    result = await stock_alerts.create_stock_alert(body, request, db)

    finnhub.add_alert.assert_called_once_with(result)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_stock_alert_duplicate_returns_409() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()
    finnhub = MagicMock()
    finnhub.validate_ticker = AsyncMock(return_value=True)
    request = _request_with_finnhub(finnhub)

    body = StockAlertCreate(ticker="AAPL", target_price=150.0, direction="below")

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.create_stock_alert(body, request, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_stock_alert_same_ticker_direction_different_alert_type_succeeds() -> None:
    """Proves the widened uniqueness constraint actually allows a buy_signal and a
    stop_loss to coexist on the same (ticker, direction) — not just in isolation."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    finnhub = MagicMock()
    finnhub.validate_ticker = AsyncMock(return_value=True)
    finnhub.add_alert = MagicMock()
    request = _request_with_finnhub(finnhub)

    buy_body = StockAlertCreate(
        ticker="AAPL", target_price=90.0, direction="below", alert_type="buy_signal"
    )
    stop_loss_body = StockAlertCreate(
        ticker="AAPL", target_price=70.0, direction="below", alert_type="stop_loss"
    )

    buy_result = await stock_alerts.create_stock_alert(buy_body, request, db)
    stop_result = await stock_alerts.create_stock_alert(stop_loss_body, request, db)

    assert buy_result.alert_type == "buy_signal"
    assert stop_result.alert_type == "stop_loss"
    assert finnhub.add_alert.call_count == 2
    assert db.commit.await_count == 2


def test_create_stock_alert_stop_loss_requires_direction_below_rejected() -> None:
    with pytest.raises(ValueError):
        StockAlertCreate(
            ticker="AAPL", target_price=100.0, direction="above", alert_type="stop_loss"
        )


def test_create_stock_alert_take_profit_requires_direction_above_rejected() -> None:
    with pytest.raises(ValueError):
        StockAlertCreate(
            ticker="AAPL", target_price=100.0, direction="below", alert_type="take_profit"
        )


@pytest.mark.asyncio
async def test_get_stock_alert_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.get_stock_alert(1, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_stock_alert_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    request = _request_with_finnhub(MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.update_stock_alert(1, StockAlertUpdate(), request, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_stock_alert_active_false_removes_from_finnhub() -> None:
    alert = _alert(active=True)
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock()
    finnhub = MagicMock()
    request = _request_with_finnhub(finnhub)

    await stock_alerts.update_stock_alert(1, StockAlertUpdate(active=False), request, db)

    finnhub.remove_alert.assert_called_once_with(alert.id, alert.ticker)
    finnhub.add_alert.assert_not_called()
    finnhub.update_alert.assert_not_called()


@pytest.mark.asyncio
async def test_update_stock_alert_active_true_adds_to_finnhub() -> None:
    alert = _alert(active=False)
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock()
    finnhub = MagicMock()
    request = _request_with_finnhub(finnhub)

    await stock_alerts.update_stock_alert(1, StockAlertUpdate(active=True), request, db)

    finnhub.add_alert.assert_called_once_with(alert)
    finnhub.remove_alert.assert_not_called()


@pytest.mark.asyncio
async def test_update_stock_alert_target_price_change_updates_finnhub_cache() -> None:
    alert = _alert(active=True, target_price=150.0)
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock()
    finnhub = MagicMock()
    request = _request_with_finnhub(finnhub)

    await stock_alerts.update_stock_alert(1, StockAlertUpdate(target_price=200.0), request, db)

    assert alert.target_price == 200.0
    finnhub.update_alert.assert_called_once_with(alert)
    finnhub.add_alert.assert_not_called()
    finnhub.remove_alert.assert_not_called()


@pytest.mark.asyncio
async def test_update_stock_alert_run_analysis_only_skips_finnhub_sync() -> None:
    """run_analysis isn't tracked by FinnhubClient's cache — no sync call needed."""
    alert = _alert(active=True, run_analysis=False)
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock()
    finnhub = MagicMock()
    request = _request_with_finnhub(finnhub)

    await stock_alerts.update_stock_alert(1, StockAlertUpdate(run_analysis=True), request, db)

    assert alert.run_analysis is True
    finnhub.update_alert.assert_not_called()
    finnhub.add_alert.assert_not_called()
    finnhub.remove_alert.assert_not_called()


@pytest.mark.asyncio
async def test_update_stock_alert_alert_type_change_syncs_finnhub_cache() -> None:
    alert = _alert(active=True, direction="below", alert_type="buy_signal")
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock()
    finnhub = MagicMock()
    request = _request_with_finnhub(finnhub)

    await stock_alerts.update_stock_alert(
        1, StockAlertUpdate(alert_type="stop_loss"), request, db
    )

    assert alert.alert_type == "stop_loss"
    finnhub.update_alert.assert_called_once_with(alert)
    finnhub.add_alert.assert_not_called()
    finnhub.remove_alert.assert_not_called()


@pytest.mark.asyncio
async def test_update_stock_alert_alert_type_direction_mismatch_returns_422() -> None:
    """alert_type=stop_loss alone against an existing direction="above" alert must be
    rejected using the merged state, since StockAlertUpdate only validates when both
    direction and alert_type are set in the same request."""
    alert = _alert(active=True, direction="above", alert_type="buy_signal")
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock()
    request = _request_with_finnhub(MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.update_stock_alert(
            1, StockAlertUpdate(alert_type="stop_loss"), request, db
        )

    assert exc_info.value.status_code == 422
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_stock_alert_duplicate_direction_returns_409() -> None:
    alert = _alert(active=True, direction="above")
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()
    request = _request_with_finnhub(MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.update_stock_alert(1, StockAlertUpdate(direction="below"), request, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_stock_alert_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    request = _request_with_finnhub(MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.delete_stock_alert(1, request, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_stock_alert_removes_from_finnhub_and_deletes() -> None:
    alert = _alert()
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    finnhub = MagicMock()
    request = _request_with_finnhub(finnhub)

    await stock_alerts.delete_stock_alert(1, request, db)

    finnhub.remove_alert.assert_called_once_with(alert.id, alert.ticker)
    db.delete.assert_awaited_once_with(alert)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_stock_alert_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.analyze_stock_alert(1, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_analyze_stock_alert_409_when_already_running() -> None:
    alert = _alert()
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)

    scalars = MagicMock()
    scalars.first.return_value = SimpleNamespace(status="pending")
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.analyze_stock_alert(1, db)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_analyze_stock_alert_creates_pending_row_with_last_price() -> None:
    alert = _alert(last_price=142.5)
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.add = MagicMock()
    db.commit = AsyncMock()

    scalars = MagicMock()
    scalars.first.return_value = None
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    with patch("app.services.trading_agents.spawn", side_effect=_closing_spawn) as spawn:
        result = await stock_alerts.analyze_stock_alert(1, db)

    assert result.stock_alert_id == alert.id
    assert result.ticker == alert.ticker
    assert result.triggered_price == 142.5
    assert result.status == "pending"
    db.commit.assert_awaited_once()
    spawn.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_stock_alert_race_duplicate_returns_409() -> None:
    """Backstop: pre-check passes but the partial unique index catches a concurrent insert."""
    alert = _alert()
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.add = MagicMock()
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()

    scalars = MagicMock()
    scalars.first.return_value = None
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.analyze_stock_alert(1, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_stock_alert_allows_null_triggered_price() -> None:
    alert = _alert(last_price=None)
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)
    db.add = MagicMock()
    db.commit = AsyncMock()

    scalars = MagicMock()
    scalars.first.return_value = None
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    with patch("app.services.trading_agents.spawn", side_effect=_closing_spawn):
        result = await stock_alerts.analyze_stock_alert(1, db)

    assert result.triggered_price is None


@pytest.mark.asyncio
async def test_list_analysis_results_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await stock_alerts.list_analysis_results(1, 10, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_analysis_results_returns_rows() -> None:
    alert = _alert()
    db = MagicMock()
    db.get = AsyncMock(return_value=alert)

    scalars = MagicMock()
    scalars.all.return_value = ["a", "b"]
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    result = await stock_alerts.list_analysis_results(1, 10, db)

    assert result == ["a", "b"]
