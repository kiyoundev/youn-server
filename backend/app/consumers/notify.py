import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.watch_item import WatchItem
from app.services.notifications import send_alert

_log = logging.getLogger(__name__)


async def handle(event: Event, session: AsyncSession) -> None:
    if event.type == "PRICE_DROP":
        title, body, url = await _format_price_drop(event, session)
    elif event.type == "STOCK_THRESHOLD":
        title, body, url = _format_stock_threshold(event)
    else:
        _log.warning("notify: unknown event type %s (id=%d) — skipping", event.type, event.id)
        return

    await send_alert(title, body, url)


async def _format_price_drop(
    event: Event, session: AsyncSession
) -> tuple[str, str, str | None]:
    payload = event.payload
    item = await session.get(WatchItem, payload["watch_item_id"])
    if item is None:
        raise ValueError(
            f"WatchItem {payload['watch_item_id']} not found for event {event.id}"
        )
    title = f"Price Drop: {item.name}"
    body = f"Now ${payload['price']:.2f} (target ${item.target_price:.2f})"
    url: str | None = payload.get("url")
    return title, body, url


def _format_stock_threshold(event: Event) -> tuple[str, str, str | None]:
    payload = event.payload
    ticker: str = payload["ticker"]
    price: float = payload["price"]
    target: float = payload["target_price"]
    direction: str = payload["direction"]
    title = f"Stock Alert: {ticker} {direction} ${target:.2f}"
    body = f"Now ${price:.4f} (target ${target:.2f} {direction})"
    return title, body, None
