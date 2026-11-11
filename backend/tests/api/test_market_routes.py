"""Tests for GET /api/market/{ticker}/history (issue #23)."""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import market


def _client(finnhub) -> TestClient:
    app = FastAPI()
    app.include_router(market.router)
    app.dependency_overrides[market.get_finnhub_client] = lambda: finnhub
    return TestClient(app, raise_server_exceptions=False)


def test_history_maps_the_finnhub_result_to_the_response_shape() -> None:
    finnhub = AsyncMock()
    finnhub.get_price_history.return_value = [
        {"date": "2026-01-01", "close": 101.5},
        {"date": "2026-01-02", "close": 102.25},
    ]

    response = _client(finnhub).get("/api/market/AAPL/history", params={"range": "1M"})

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2026-01-01", "close": 101.5},
        {"date": "2026-01-02", "close": 102.25},
    ]
    finnhub.get_price_history.assert_awaited_once_with("AAPL", "1M", None)


def test_history_passes_native_currency_through_to_get_price_history() -> None:
    finnhub = AsyncMock()
    finnhub.get_price_history.return_value = []

    _client(finnhub).get("/api/market/RY/history", params={"range": "1M", "native_currency": "CAD"})

    finnhub.get_price_history.assert_awaited_once_with("RY", "1M", "CAD")


def test_an_invalid_range_422s() -> None:
    response = _client(AsyncMock()).get("/api/market/AAPL/history", params={"range": "bogus"})
    assert response.status_code == 422


def test_an_invalid_native_currency_422s() -> None:
    response = _client(AsyncMock()).get(
        "/api/market/AAPL/history", params={"range": "1M", "native_currency": "GBP"}
    )
    assert response.status_code == 422


def test_a_missing_required_range_422s() -> None:
    response = _client(AsyncMock()).get("/api/market/AAPL/history")
    assert response.status_code == 422


def test_an_upstream_failure_is_an_empty_list_not_an_error() -> None:
    # mirrors get_price_history's own never-raise contract: [] on failure, logged
    finnhub = AsyncMock()
    finnhub.get_price_history.return_value = []

    response = _client(finnhub).get("/api/market/AAPL/history", params={"range": "1M"})

    assert response.status_code == 200
    assert response.json() == []
