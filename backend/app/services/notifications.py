import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import httpx

from app.core.config import settings

_log = logging.getLogger(__name__)

_PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


async def send_pushover(
    title: str, body: str, url: str | None = None, priority: int = 0
) -> None:
    if not settings.pushover_api_token or not settings.pushover_user_key:
        _log.warning("Pushover credentials not configured — skipping")
        return

    payload: dict = {
        "token": settings.pushover_api_token,
        "user": settings.pushover_user_key,
        "title": title,
        "message": body,
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "View"
    if priority:
        # Priority 2 ("emergency") additionally requires retry/expire params to
        # repeat until acknowledged — not used anywhere yet, so not wired here.
        payload["priority"] = priority

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(_PUSHOVER_URL, data=payload)
        resp.raise_for_status()
    _log.info("Pushover sent: %s", title)


def _send_email_sync(title: str, body: str, url: str | None = None) -> None:
    if not settings.gmail_user or not settings.gmail_app_password:
        _log.warning("Gmail credentials not configured — skipping")
        return

    html_parts = [
        "<html><body>",
        f"<h2>{escape(title)}</h2>",
        f"<p>{escape(body)}</p>",
    ]
    if url:
        html_parts.append(f'<p><a href="{escape(url)}">View</a></p>')
    html_parts.append("</body></html>")
    html = "\n".join(html_parts)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = title
    msg["From"] = settings.gmail_user
    msg["To"] = settings.gmail_user
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(settings.gmail_user, settings.gmail_app_password)
        smtp.sendmail(settings.gmail_user, settings.gmail_user, msg.as_string())
    _log.info("Email sent: %s", title)


async def send_email(title: str, body: str, url: str | None = None) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_email_sync, title, body, url)


async def send_alert(title: str, body: str, url: str | None = None, priority: int = 0) -> None:
    if settings.notify_pushover:
        try:
            await send_pushover(title, body, url, priority)
        except httpx.TimeoutException:
            _log.warning("Pushover timeout — transient, not retrying")
        except httpx.NetworkError as exc:
            _log.warning("Pushover network error: %s", exc)
        except httpx.HTTPStatusError as exc:
            _log.error(
                "Pushover API error %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
        except Exception:
            _log.error("Pushover unexpected error", exc_info=True)

    if settings.notify_email:
        try:
            await send_email(title, body, url)
        except smtplib.SMTPAuthenticationError:
            _log.error("Gmail auth failed — check app password in settings")
        except smtplib.SMTPConnectError as exc:
            _log.warning("Gmail connect failed: %s", exc)
        except smtplib.SMTPException as exc:
            _log.error("Gmail SMTP error: %s", exc)
        except Exception:
            _log.error("Email unexpected error", exc_info=True)
