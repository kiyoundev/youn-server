import logging

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
