from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.core.config import settings
from app.services import notifications


@pytest.fixture(autouse=True)
def _restore_notify_settings(monkeypatch):
    monkeypatch.setattr(settings, "notify_pushover", True)
    monkeypatch.setattr(settings, "pushover_api_token", "")
    monkeypatch.setattr(settings, "pushover_user_key", "")


@pytest.mark.asyncio
@respx.mock
async def test_send_pushover_posts_payload_with_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "pushover_api_token", "app-token")
    monkeypatch.setattr(settings, "pushover_user_key", "user-key")

    route = respx.post("https://api.pushover.net/1/messages.json").mock(
        return_value=httpx.Response(200, json={"status": 1})
    )

    await notifications.send_pushover("Test title", "Test body", "https://example.com")

    assert route.called
    payload = route.calls.last.request.content.decode()
    assert "token=app-token" in payload
    assert "user=user-key" in payload
    assert "title=Test+title" in payload
    assert "message=Test+body" in payload
    assert "url=https%3A%2F%2Fexample.com" in payload
    assert "url_title=View" in payload


@pytest.mark.asyncio
@respx.mock
async def test_send_pushover_posts_payload_without_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "pushover_api_token", "app-token")
    monkeypatch.setattr(settings, "pushover_user_key", "user-key")

    route = respx.post("https://api.pushover.net/1/messages.json").mock(
        return_value=httpx.Response(200, json={"status": 1})
    )

    await notifications.send_pushover("Test title", "Test body")

    assert route.called
    payload = route.calls.last.request.content.decode()
    assert "url=" not in payload
    assert "url_title=" not in payload


@pytest.mark.asyncio
@respx.mock
async def test_send_pushover_includes_priority_when_nonzero(monkeypatch) -> None:
    monkeypatch.setattr(settings, "pushover_api_token", "app-token")
    monkeypatch.setattr(settings, "pushover_user_key", "user-key")

    route = respx.post("https://api.pushover.net/1/messages.json").mock(
        return_value=httpx.Response(200, json={"status": 1})
    )

    await notifications.send_pushover("Stop-loss", "Sell now", priority=1)

    payload = route.calls.last.request.content.decode()
    assert "priority=1" in payload


@pytest.mark.asyncio
@respx.mock
async def test_send_pushover_omits_priority_when_zero(monkeypatch) -> None:
    monkeypatch.setattr(settings, "pushover_api_token", "app-token")
    monkeypatch.setattr(settings, "pushover_user_key", "user-key")

    route = respx.post("https://api.pushover.net/1/messages.json").mock(
        return_value=httpx.Response(200, json={"status": 1})
    )

    await notifications.send_pushover("Normal", "Body")

    payload = route.calls.last.request.content.decode()
    assert "priority=" not in payload


@pytest.mark.asyncio
@respx.mock
async def test_send_pushover_skips_without_credentials() -> None:
    route = respx.post("https://api.pushover.net/1/messages.json").mock(
        return_value=httpx.Response(200)
    )

    await notifications.send_pushover("Test", "Body")

    assert route.called is False


@pytest.mark.asyncio
async def test_send_alert_calls_pushover_when_enabled() -> None:
    with patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover:
        await notifications.send_alert("Title", "Body", "https://example.com")

    send_pushover.assert_awaited_once_with("Title", "Body", "https://example.com", 0)


@pytest.mark.asyncio
async def test_send_alert_pushover_failure_does_not_raise() -> None:
    with patch(
        "app.services.notifications.send_pushover",
        new=AsyncMock(side_effect=RuntimeError("pushover down")),
    ) as send_pushover:
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_alert_skips_pushover_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "notify_pushover", False)

    with patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover:
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_not_awaited()
