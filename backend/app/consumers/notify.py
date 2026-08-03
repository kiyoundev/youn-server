import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.product import Product
from app.services.notifications import send_alert

_log = logging.getLogger(__name__)

_PRIORITY_NORMAL = 0
_PRIORITY_HIGH = 1


async def handle(event: Event, session: AsyncSession) -> None:
    if event.type == "PRICE_DROP":
        title, body, url, priority = await _format_price_drop(event, session)
    elif event.type == "STOCK_THRESHOLD":
        title, body, url, priority = _format_stock_threshold(event)
    else:
        _log.warning("notify: unknown event type %s (id=%d) — skipping", event.type, event.id)
        return

    await send_alert(title, body, url, priority)


async def _format_price_drop(
    event: Event, session: AsyncSession
) -> tuple[str, str, str | None, int]:
    payload = event.payload
    product = await session.get(Product, payload["product_id"])
    if product is None:
        raise ValueError(
            f"Product {payload['product_id']} not found for event {event.id}"
        )
    title = f"Price Drop: {product.name}"
    body = f"Now ${payload['price']:.2f} at {payload['retailer']} (target ${product.target_price:.2f})"
    url: str | None = payload.get("url")
    return title, body, url, _PRIORITY_NORMAL


def _format_stock_threshold(event: Event) -> tuple[str, str, str | None, int]:
    payload = event.payload
    ticker: str = payload["ticker"]
    price: float = payload["price"]
    target: float = payload["target_price"]
    direction: str = payload["direction"]
    alert_type: str = payload.get("alert_type", "buy_signal")

    if alert_type == "stop_loss":
        title = f"STOP-LOSS: SELL {ticker} NOW"
        body = f"${price:.4f} hit stop of ${target:.2f} — sell as soon as possible"
        priority = _PRIORITY_HIGH
    elif alert_type == "take_profit":
        title = f"Take Profit: {ticker} hit ${target:.2f}"
        body = f"${price:.4f} reached target of ${target:.2f} — consider selling to lock in gains"
        priority = _PRIORITY_NORMAL
    else:
        title = f"Stock Alert: {ticker} {direction} ${target:.2f}"
        body = f"Now ${price:.4f} (target ${target:.2f} {direction})"
        priority = _PRIORITY_NORMAL

    return title, body, None, priority
