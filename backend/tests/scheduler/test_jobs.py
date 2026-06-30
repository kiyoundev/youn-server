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


def _watch_item(
    item_id: int = 1,
    *,
    active: bool = True,
    target_price: float = 100.0,
    alerted_at: dt.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id,
        name="Item",
        url="https://example.com/item",
        scraper_type=None,
        active=active,
        target_price=target_price,
        alerted_at=alerted_at,
        last_price=None,
    )


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
    item = _watch_item(item_id=7, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=item)
    session.commit = AsyncMock()

    def _assign_event_id(obj):
        if obj.__class__.__name__ == "Event":
            obj.id = 55

    session.add = MagicMock(side_effect=_assign_event_id)

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(7, router, queue)

    assert session.add.call_count == 2
    assert item.last_price == 90.0
    assert item.alerted_at is not None
    session.commit.assert_awaited_once()
    assert await queue.get() == 55


@pytest.mark.asyncio
async def test_process_item_blocks_duplicate_drop_when_alerted() -> None:
    alerted = dt.datetime.now(dt.timezone.utc)
    item = _watch_item(item_id=8, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(return_value=item)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(8, router, queue)

    assert session.add.call_count == 1
    session.commit.assert_awaited_once()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_recovery_clears_alerted_at() -> None:
    alerted = dt.datetime.now(dt.timezone.utc)
    item = _watch_item(item_id=9, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(return_value=item)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=120.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(9, router, queue)

    assert item.alerted_at is None
    assert session.add.call_count == 1
    session.commit.assert_awaited_once()
    assert queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scrape",
    [
        ScraperResult(price=None, status="oos"),
        ScraperResult(price=None, status="error"),
        ScraperResult(price=None, status="ok"),
    ],
)
async def test_process_item_skips_non_writable_scrape_results(scrape: ScraperResult) -> None:
    item = _watch_item(item_id=10, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=item)
    session.commit = AsyncMock()
    session.add = MagicMock()

    router = MagicMock()
    router.get_price = AsyncMock(return_value=scrape)

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs._process_item(10, router, queue)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    assert queue.empty()
