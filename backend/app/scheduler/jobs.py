import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models.event import Event
from app.models.price_history import PriceHistory
from app.models.watch_item import WatchItem
from app.services.scraper.router import RetailerRouter

_log = logging.getLogger(__name__)


async def poll_prices(queue: asyncio.Queue) -> None:
    _log.info("poll_prices: starting cycle")
    router = RetailerRouter()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WatchItem.id).where(WatchItem.active == True)  # noqa: E712
        )
        item_ids: list[int] = result.scalars().all()

    _log.info("poll_prices: %d active items", len(item_ids))

    for item_id in item_ids:
        try:
            await _process_item(item_id, router, queue)
        except Exception:
            _log.error("poll_prices: unhandled error for item %d", item_id, exc_info=True)

    _log.info("poll_prices: cycle complete")


async def _process_item(item_id: int, router: RetailerRouter, queue: asyncio.Queue) -> None:
    async with AsyncSessionLocal() as session:
        item = await session.get(WatchItem, item_id)
        if not item or not item.active:
            return

        scrape = await router.get_price(item.url, scraper_type=item.scraper_type)

        if scrape.status == "oos":
            _log.info("item %d (%s) out of stock", item.id, item.name)
            return

        if scrape.status == "error":
            _log.warning("scraper error for item %d (%s)", item.id, item.name)
            return

        if scrape.price is None:
            _log.warning("scraper returned ok with None price for item %d (%s), skipping", item.id, item.name)
            return

        now = datetime.now(timezone.utc)
        session.add(PriceHistory(watch_item_id=item.id, price=scrape.price))
        item.last_price = scrape.price

        if scrape.price <= item.target_price and item.alerted_at is None:
            event = Event(
                type="PRICE_DROP",
                payload={"watch_item_id": item.id, "price": scrape.price, "url": item.url},
                status="pending",
            )
            session.add(event)
            item.alerted_at = now
            await session.commit()
            await queue.put(event.id)
            _log.info(
                "PRICE_DROP: item %d (%s) @ %.2f (target %.2f)",
                item.id, item.name, scrape.price, item.target_price,
            )
        elif scrape.price > item.target_price and item.alerted_at is not None:
            item.alerted_at = None
            await session.commit()
            _log.info("item %d (%s) re-armed (price recovered)", item.id, item.name)
        else:
            await session.commit()
