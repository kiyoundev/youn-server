import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.scheduler import jobs
from app.services.scraper.result import ScraperResult


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _listing(
    item_id: int = 1,
    *,
    active: bool = True,
    retailer: str = "amazon_ca",
    product_id: int = 1,
    last_price: float | None = None,
    last_scrape_status: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id,
        url=f"https://example.com/item-{item_id}",
        retailer=retailer,
        scraper_type=None,
        active=active,
        product_id=product_id,
        last_price=last_price,
        last_scrape_status=last_scrape_status,
    )


def _product(
    product_id: int = 1,
    *,
    name="Item",
    target_price: float = 100.0,
    alerted_at: dt.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(id=product_id, name=name, target_price=target_price, alerted_at=alerted_at)


def _active_listings_result(listings: list[SimpleNamespace]) -> MagicMock:
    scalars = MagicMock()
    scalars.all.return_value = listings
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_poll_prices_processes_all_active_items() -> None:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [1, 2, 3]
    result.scalars.return_value = scalars

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.RetailerRouter") as router_cls,
        patch("app.scheduler.jobs._process_item", new=AsyncMock()) as process_item,
    ):
        queue = asyncio.Queue()
        await jobs.poll_prices(queue)

    router = router_cls.return_value
    process_item.assert_any_await(1, router, queue)
    process_item.assert_any_await(2, router, queue)
    process_item.assert_any_await(3, router, queue)
    assert process_item.await_count == 3


@pytest.mark.asyncio
async def test_poll_prices_skips_when_lock_already_held() -> None:
    with (
        patch("app.scheduler.jobs.RetailerRouter") as router_cls,
        patch("app.scheduler.jobs._process_item", new=AsyncMock()) as process_item,
    ):
        async with jobs._prices_lock:
            queue = asyncio.Queue()
            await jobs.poll_prices(queue)

    router_cls.assert_not_called()
    process_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_prices_continues_when_item_processing_errors() -> None:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [1, 2, 3]
    result.scalars.return_value = scalars

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    process = AsyncMock(side_effect=[None, RuntimeError("boom"), None])
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.RetailerRouter") as router_cls,
        patch("app.scheduler.jobs._process_item", new=process),
    ):
        queue = asyncio.Queue()
        await jobs.poll_prices(queue)

    router = router_cls.return_value
    process.assert_any_await(1, router, queue)
    process.assert_any_await(2, router, queue)
    process.assert_any_await(3, router, queue)
    assert process.await_count == 3


@pytest.mark.asyncio
async def test_process_item_writes_history_and_price_drop_event() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[listing, product])
    session.commit = AsyncMock()
    session.execute = AsyncMock(return_value=_active_listings_result([listing]))

    def _assign_event_id(obj):
        if obj.__class__.__name__ == "Event":
            obj.id = 55

    session.add = MagicMock(side_effect=_assign_event_id)

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(7, router, queue)

    assert session.add.call_count == 2  # PriceHistory + Event
    assert listing.last_price == 90.0
    assert listing.last_scrape_status == "ok"
    assert product.alerted_at is not None
    session.commit.assert_awaited_once()
    assert await queue.get() == 55


@pytest.mark.asyncio
async def test_process_item_blocks_duplicate_drop_when_alerted() -> None:
    alerted = dt.datetime.now(dt.timezone.utc)
    listing = _listing(item_id=8, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[listing, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([listing]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(8, router, queue)

    assert session.add.call_count == 1  # PriceHistory only, no new Event (already alerted)
    assert product.alerted_at == alerted  # unchanged
    session.commit.assert_awaited_once()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_recovery_clears_alerted_at() -> None:
    alerted = dt.datetime.now(dt.timezone.utc)
    listing = _listing(item_id=9, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[listing, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([listing]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=120.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(9, router, queue)

    assert product.alerted_at is None
    assert session.add.call_count == 1
    session.commit.assert_awaited_once()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_ignores_inactive_sibling_listing_when_recomputing_cheapest() -> None:
    """A paused sibling listing with a stale, very low last_price must not
    drag the recomputed minimum below what active listings actually offer."""
    scraped = _listing(item_id=20, product_id=1, retailer="amazon_ca")
    paused_sibling = _listing(item_id=21, product_id=1, retailer="bestbuy_ca", active=False, last_price=1.0)
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[scraped, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    # Query is scoped to active==True, so the paused sibling is correctly
    # excluded by the DB in real usage — the mock reflects that filtering.
    session.execute = AsyncMock(return_value=_active_listings_result([scraped]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=120.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(20, router, queue)

    assert paused_sibling.last_price == 1.0  # untouched
    assert product.alerted_at is None  # 120 > 100, never triggered
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_excludes_oos_listing_stale_price_from_cheapest() -> None:
    """An 'oos' listing's last_price is frozen at whatever it was before it
    disappeared — it must not count toward the cheapest-active-listing
    comparison, or a phantom stale price could fire (or permanently hold
    open) an alert for a product that isn't actually purchasable there."""
    scraped = _listing(item_id=40, product_id=1, retailer="amazon_ca")
    oos_sibling = _listing(
        item_id=41,
        product_id=1,
        retailer="bestbuy_ca",
        active=True,
        last_price=50.0,
        last_scrape_status="oos",
    )
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[scraped, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([scraped, oos_sibling]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=150.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(40, router, queue)

    # Without the fix, oos_sibling's stale $50 would win and incorrectly
    # trigger (50 <= 100), even though nothing is actually available there.
    assert product.alerted_at is None
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_recovery_not_blocked_by_stale_oos_sibling() -> None:
    """The permanent-suppression form of the same bug: once alerted, a
    stale oos price must not prevent alerted_at from ever clearing, since
    that would silently block all future alerts for this product."""
    alerted = dt.datetime.now(dt.timezone.utc)
    scraped = _listing(item_id=50, product_id=1, retailer="amazon_ca")
    oos_sibling = _listing(
        item_id=51,
        product_id=1,
        retailer="bestbuy_ca",
        active=True,
        last_price=50.0,
        last_scrape_status="oos",
    )
    product = _product(product_id=1, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[scraped, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([scraped, oos_sibling]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=150.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(50, router, queue)

    # Without the fix, oos_sibling's stale $50 would keep "cheapest" <= 100
    # forever, so alerted_at would never clear even though the only
    # available listing has recovered to $150.
    assert product.alerted_at is None
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_unrelated_active_listing_does_not_incorrectly_rearm() -> None:
    """The bug this rewrite exists to prevent: BestBuy already triggered the
    alert at $340 (target $350). Amazon's own routine poll comes back at
    $398 (unchanged, still above target) — that must NOT clear the product's
    alerted_at, since the product is still a deal via BestBuy."""
    alerted = dt.datetime.now(dt.timezone.utc)
    amazon = _listing(item_id=30, product_id=1, retailer="amazon_ca", last_price=398.0)
    bestbuy = _listing(item_id=31, product_id=1, retailer="bestbuy_ca", last_price=340.0, last_scrape_status="ok")
    product = _product(product_id=1, target_price=350.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[amazon, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([amazon, bestbuy]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=398.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(30, router, queue)

    assert product.alerted_at == alerted  # still armed — BestBuy is still under target
    assert queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["oos", "error"])
async def test_process_item_persists_scrape_status_on_oos_or_error(status: str) -> None:
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status=status))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(10, router, queue)

    assert listing.last_scrape_status == status
    session.add.assert_not_called()  # no PriceHistory row — no price to record
    session.commit.assert_awaited_once()  # but the status write is persisted
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_skips_ok_status_with_none_price() -> None:
    """Anomalous combination (status=ok but no price) — nothing meaningful
    happened, so nothing is written at all, unlike oos/error."""
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(10, router, queue)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_broadcasts_after_successful_scrape() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[listing, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([listing]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=120.0, status="ok"))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs._process_item(7, router, queue)

    broadcast_mock.assert_called_once_with({"product_id": 1, "listing_id": 7})


@pytest.mark.asyncio
async def test_process_item_broadcast_uses_scraped_listing_not_cheapest_winner() -> None:
    """Regression: the broadcast must carry the listing that was actually
    scraped (item 7), not `winning` (the alert Event's cheapest-listing
    field) — those differ whenever a sibling retailer is cheaper."""
    scraped = _listing(item_id=7, product_id=1, retailer="amazon_ca")
    cheaper_sibling = _listing(item_id=8, product_id=1, retailer="bestbuy_ca", last_price=50.0, last_scrape_status="ok")
    product = _product(product_id=1, target_price=200.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(side_effect=[scraped, product])
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_active_listings_result([scraped, cheaper_sibling]))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=180.0, status="ok"))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs._process_item(7, router, queue)

    broadcast_mock.assert_called_once_with({"product_id": 1, "listing_id": 7})  # not 8


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["oos", "error"])
async def test_process_item_does_not_broadcast_on_oos_or_error(status: str) -> None:
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status=status))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs._process_item(10, router, queue)

    broadcast_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_item_does_not_broadcast_when_ok_status_has_none_price() -> None:
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status="ok"))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs._process_item(10, router, queue)

    broadcast_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_item_does_not_broadcast_for_an_inactive_listing() -> None:
    listing = _listing(item_id=10, active=False)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)

    router = MagicMock()
    router.get_price = AsyncMock()

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs._process_item(10, router, queue)

    router.get_price.assert_not_called()
    broadcast_mock.assert_not_called()


def _finnhub_mock(tickers: list[str], prices: dict[str, float | None]) -> MagicMock:
    finnhub = MagicMock()
    finnhub.cached_tickers.return_value = tickers
    finnhub.get_price = AsyncMock(side_effect=lambda t: prices.get(t))
    finnhub.check_threshold = AsyncMock()
    return finnhub


@pytest.mark.asyncio
async def test_poll_stocks_checks_all_cached_tickers() -> None:
    finnhub = _finnhub_mock(["AAPL", "TSLA"], {"AAPL": 150.0, "TSLA": 200.0})

    await jobs.poll_stocks(finnhub)

    finnhub.check_threshold.assert_any_await("AAPL", 150.0)
    finnhub.check_threshold.assert_any_await("TSLA", 200.0)
    assert finnhub.check_threshold.await_count == 2


@pytest.mark.asyncio
async def test_poll_stocks_skips_ticker_with_none_price() -> None:
    finnhub = _finnhub_mock(["AAPL"], {"AAPL": None})

    await jobs.poll_stocks(finnhub)

    finnhub.check_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_stocks_continues_when_ticker_processing_errors() -> None:
    finnhub = MagicMock()
    finnhub.cached_tickers.return_value = ["AAPL", "TSLA"]
    finnhub.get_price = AsyncMock(side_effect=[RuntimeError("boom"), 200.0])
    finnhub.check_threshold = AsyncMock()

    await jobs.poll_stocks(finnhub)

    finnhub.check_threshold.assert_awaited_once_with("TSLA", 200.0)


@pytest.mark.asyncio
async def test_poll_stocks_skips_when_lock_already_held() -> None:
    finnhub = _finnhub_mock(["AAPL"], {"AAPL": 150.0})

    async with jobs._stocks_lock:
        await jobs.poll_stocks(finnhub)

    finnhub.cached_tickers.assert_not_called()
    finnhub.check_threshold.assert_not_awaited()
