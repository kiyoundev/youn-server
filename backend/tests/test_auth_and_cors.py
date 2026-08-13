from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import get_db
from app.main import app


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
