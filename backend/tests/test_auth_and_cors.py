from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import positions
from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.services.ledger_cache import LedgerSnapshot


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "api_key", "secret-test-key")
    return TestClient(app, raise_server_exceptions=False)


def test_health_requires_no_auth(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_items_route_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/api/items")
    assert response.status_code == 401


def test_items_route_wrong_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/api/items", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_items_route_correct_api_key_passes_auth(client: TestClient) -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.get("/api/items", headers={"X-API-Key": "secret-test-key"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == []


def test_empty_configured_api_key_rejects_empty_header(monkeypatch) -> None:
    """Regression: an unset API_KEY must fail closed, not accept an empty X-API-Key header."""
    monkeypatch.setattr(settings, "api_key", "")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/items", headers={"X-API-Key": ""})

    assert response.status_code == 401


def test_empty_configured_api_key_rejects_missing_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_key", "")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/items")

    assert response.status_code == 401


def test_stocks_route_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/api/stockalerts")
    assert response.status_code == 401


def test_poll_route_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.post("/api/poll/prices")
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/api/positions", "/api/portfolio/summary"])
def test_portfolio_routes_missing_api_key_returns_401(client: TestClient, path: str) -> None:
    # 401 and not 404 also proves positions.router is included in main.py: an
    # unregistered route would 404 before auth ever ran.
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/positions", "/api/portfolio/summary"])
def test_portfolio_routes_wrong_api_key_returns_401(client: TestClient, path: str) -> None:
    assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401


def test_portfolio_route_correct_api_key_reaches_the_handler(client: TestClient) -> None:
    ledger = SimpleNamespace(get=AsyncMock(return_value=LedgerSnapshot((), cash=0.0)))
    prices = SimpleNamespace(get_prices=AsyncMock(return_value={}))

    async def _override_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[positions.get_ledger_cache] = lambda: ledger
    app.dependency_overrides[positions.get_price_service] = lambda: prices
    try:
        response = client.get("/api/positions", headers={"X-API-Key": "secret-test-key"})
    finally:
        for dependency in (get_db, positions.get_ledger_cache, positions.get_price_service):
            app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 200
    assert response.json() == []


def test_openapi_declares_the_api_key_scheme(client: TestClient) -> None:
    # This is what gives Swagger UI its Authorize button.
    schema = client.get("/openapi.json").json()

    assert schema["components"]["securitySchemes"]["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }


def test_protected_operations_require_the_scheme_and_health_does_not(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert {"APIKeyHeader": []} in paths["/api/positions"]["get"]["security"]
    assert {"APIKeyHeader": []} in paths["/api/items"]["get"]["security"]
    assert "security" not in paths["/api/health"]["get"]


def test_cors_preflight_allows_configured_origin(client: TestClient) -> None:
    # CORSMiddleware reads settings.cors_origins at import time (app.main module load);
    # default is "http://localhost:3000" per app.core.config.Settings.
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
