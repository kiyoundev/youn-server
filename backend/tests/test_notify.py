from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from app.core.config import settings
from app.services import notifications


@pytest.fixture(autouse=True)
def _restore_notify_settings(monkeypatch):
    monkeypatch.setattr(settings, "notify_pushover", True)
    monkeypatch.setattr(settings, "notify_email", True)
    monkeypatch.setattr(settings, "pushover_api_token", "")
    monkeypatch.setattr(settings, "pushover_user_key", "")
    monkeypatch.setattr(settings, "gmail_user", "")
    monkeypatch.setattr(settings, "gmail_app_password", "")


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


def test_send_email_sync_sends_html_body(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gmail_user", "test@example.com")
    monkeypatch.setattr(settings, "gmail_app_password", "app-password")

    smtp_instance = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp_instance
    smtp_cm.__exit__.return_value = False

    with patch("app.services.notifications.smtplib.SMTP", return_value=smtp_cm) as smtp_cls:
        notifications._send_email_sync("Hello", "Price dropped", "https://example.com/item")

    smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
    assert smtp_instance.ehlo.call_count == 2
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("test@example.com", "app-password")
    smtp_instance.sendmail.assert_called_once()

    sendmail_args = smtp_instance.sendmail.call_args.args
    raw_msg = sendmail_args[2]
    assert "Subject: Hello" in raw_msg
    assert "Price dropped" in raw_msg
    assert "https://example.com/item" in raw_msg


def test_send_email_sync_skips_without_credentials() -> None:
    with patch("app.services.notifications.smtplib.SMTP") as smtp_cls:
        notifications._send_email_sync("Hello", "Body")

    smtp_cls.assert_not_called()


@pytest.mark.asyncio
async def test_send_email_runs_sync_in_executor() -> None:
    with patch("app.services.notifications._send_email_sync") as send_sync:
        await notifications.send_email("Title", "Body", "https://example.com")

    send_sync.assert_called_once_with("Title", "Body", "https://example.com")


@pytest.mark.asyncio
async def test_send_alert_calls_both_channels_when_enabled() -> None:
    with (
        patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover,
        patch("app.services.notifications.send_email", new=AsyncMock()) as send_email,
    ):
        await notifications.send_alert("Title", "Body", "https://example.com")

    send_pushover.assert_awaited_once_with("Title", "Body", "https://example.com", 0)
    send_email.assert_awaited_once_with("Title", "Body", "https://example.com")


@pytest.mark.asyncio
async def test_send_alert_pushover_failure_does_not_block_email() -> None:
    with (
        patch(
            "app.services.notifications.send_pushover",
            new=AsyncMock(side_effect=RuntimeError("pushover down")),
        ) as send_pushover,
        patch("app.services.notifications.send_email", new=AsyncMock()) as send_email,
    ):
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_awaited_once()
    send_email.assert_awaited_once_with("Title", "Body", None)


@pytest.mark.asyncio
async def test_send_alert_email_failure_does_not_block_pushover() -> None:
    with (
        patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover,
        patch(
            "app.services.notifications.send_email",
            new=AsyncMock(side_effect=RuntimeError("smtp down")),
        ) as send_email,
    ):
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_awaited_once_with("Title", "Body", None, 0)
    send_email.assert_awaited_once_with("Title", "Body", None)


@pytest.mark.asyncio
async def test_send_alert_pushover_only(monkeypatch) -> None:
    monkeypatch.setattr(settings, "notify_pushover", True)
    monkeypatch.setattr(settings, "notify_email", False)

    with (
        patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover,
        patch("app.services.notifications.send_email", new=AsyncMock()) as send_email,
    ):
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_awaited_once_with("Title", "Body", None, 0)
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_alert_email_only(monkeypatch) -> None:
    monkeypatch.setattr(settings, "notify_pushover", False)
    monkeypatch.setattr(settings, "notify_email", True)

    with (
        patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover,
        patch("app.services.notifications.send_email", new=AsyncMock()) as send_email,
    ):
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_not_awaited()
    send_email.assert_awaited_once_with("Title", "Body", None)


@pytest.mark.asyncio
async def test_send_alert_both_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "notify_pushover", False)
    monkeypatch.setattr(settings, "notify_email", False)

    with (
        patch("app.services.notifications.send_pushover", new=AsyncMock()) as send_pushover,
        patch("app.services.notifications.send_email", new=AsyncMock()) as send_email,
    ):
        await notifications.send_alert("Title", "Body")

    send_pushover.assert_not_awaited()
    send_email.assert_not_awaited()
