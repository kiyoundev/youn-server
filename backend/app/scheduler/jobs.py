import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models.event import Event
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.watch_item import Listing
from app.services.scraper.router import RetailerRouter
from app.services.stocks import FinnhubClient

_log = logging.getLogger(__name__)

_prices_lock = asyncio.Lock()
_stocks_lock = asyncio.Lock()


async def poll_prices(queue: asyncio.Queue) -> None:
    if _prices_lock.locked():
        _log.warning("poll_prices: skipping — previous cycle still running")
        return

    async with _prices_lock:
        _log.info("poll_prices: starting cycle")
        router = RetailerRouter()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Listing.id).where(Listing.active == True)  # noqa: E712
            )
            item_ids: list[int] = result.scalars().all()

        _log.info("poll_prices: %d active items", len(item_ids))

        for item_id in item_ids:
            try:
                await _process_item(item_id, router, queue)
            except Exception:
                _log.error("poll_prices: unhandled error for item %d", item_id, exc_info=True)

        _log.info("poll_prices: cycle complete")


async def poll_stocks(finnhub: FinnhubClient) -> None:
    if _stocks_lock.locked():
        _log.warning("poll_stocks: skipping — previous cycle still running")
        return

    async with _stocks_lock:
        tickers = finnhub.cached_tickers()
        _log.info("poll_stocks: re-checking %d cached ticker(s)", len(tickers))

        for ticker in tickers:
            try:
                price = await finnhub.get_price(ticker)
                if price is not None:
                    await finnhub.check_threshold(ticker, price)
            except Exception:
                _log.error("poll_stocks: unhandled error for %s", ticker, exc_info=True)

        _log.info("poll_stocks: cycle complete")


async def _process_item(item_id: int, router: RetailerRouter, queue: asyncio.Queue) -> None:
    async with AsyncSessionLocal() as session:
        listing = await session.get(Listing, item_id)
        if not listing or not listing.active:
            return

        scrape = await router.get_price(listing.url, scraper_type=listing.scraper_type)

        if scrape.status == "oos":
            _log.info("listing %d (%s) out of stock", listing.id, listing.retailer)
            listing.last_scrape_status = "oos"
            await session.commit()
            return

        if scrape.status == "error":
            _log.warning("scraper error for listing %d (%s)", listing.id, listing.retailer)
            listing.last_scrape_status = "error"
            await session.commit()
            return

        if scrape.price is None:
            _log.warning(
                "scraper returned ok with None price for listing %d (%s), skipping",
                listing.id, listing.retailer,
            )
            return

        now = datetime.now(timezone.utc)
        session.add(PriceHistory(watch_item_id=listing.id, price=scrape.price))
        listing.last_price = scrape.price
        listing.last_scrape_status = "ok"

        product = await session.get(Product, listing.product_id)

        active_listings_result = await session.execute(
            select(Listing).where(Listing.product_id == product.id, Listing.active == True)  # noqa: E712
        )
        active_listings = list(active_listings_result.scalars().all())
        # Only listings confirmed available ("ok") are eligible — an "oos"
        # listing's last_price is frozen at whatever it was before it
        # disappeared, and letting that stale price win the comparison would
        # make it permanently block future alerts (it can never be beaten,
        # so alerted_at would never clear even after it recovers elsewhere).
        # The just-scraped `listing` is always "ok" here, so this is never empty.
        available_listings = [
            l for l in active_listings if l.last_price is not None and l.last_scrape_status == "ok"
        ]
        winning = min(available_listings, key=lambda l: l.last_price)
        cheapest = winning.last_price

        if cheapest <= product.target_price and product.alerted_at is None:
            event = Event(
                type="PRICE_DROP",
                payload={
                    "product_id": product.id,
                    "listing_id": winning.id,
                    "retailer": winning.retailer,
                    "price": cheapest,
                    "url": winning.url,
                },
                status="pending",
            )
            session.add(event)
            product.alerted_at = now
            await session.commit()
            await queue.put(event.id)
            _log.info(
                "PRICE_DROP: product %d (%s) @ %.2f (target %.2f) via %s",
                product.id, product.name, cheapest, product.target_price, winning.retailer,
            )
        elif cheapest > product.target_price and product.alerted_at is not None:
            product.alerted_at = None
            await session.commit()
            _log.info("product %d (%s) re-armed (price recovered)", product.id, product.name)
        else:
            await session.commit()
