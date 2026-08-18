import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.main import lifespan


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_scheduler_and_finnhub() -> None:
    app = SimpleNamespace(state=SimpleNamespace())

    finnhub = MagicMock()
    finnhub.start = AsyncMock()
    finnhub.stop = AsyncMock()

    scheduler = MagicMock()
    db_result = MagicMock()
    db_scalars = MagicMock()
    db_scalars.all.return_value = []
    db_result.scalars.return_value = db_scalars
    db_session = MagicMock()
    db_session.execute = AsyncMock(return_value=db_result)

    with (
        patch("app.main.AsyncSessionLocal", return_value=_AsyncCM(db_session)),
        patch("app.main.FinnhubClient", return_value=finnhub) as finnhub_cls,
        patch("app.main.AsyncIOScheduler", return_value=scheduler) as scheduler_cls,
        patch("app.main.dispatcher.run", new=AsyncMock()) as dispatcher_run,
        patch("app.main.PatchrightScraper.close_browser", new=AsyncMock()) as close_browser,
    ):
        async with lifespan(app):
            await asyncio.sleep(0)
            finnhub.start.assert_awaited_once()
            scheduler.start.assert_called_once()

            assert hasattr(app.state, "event_queue")
            assert app.state.finnhub is finnhub
            assert app.state.scheduler is scheduler
            assert isinstance(app.state.dispatch_task, asyncio.Task)

            finnhub_cls.assert_called_once_with(event_queue=app.state.event_queue)
            scheduler_cls.assert_called_once()
            dispatcher_run.assert_awaited_once_with(app.state.event_queue)

            assert scheduler.add_job.call_count == 1
            (poll_prices_call,) = scheduler.add_job.call_args_list

            assert poll_prices_call.args[1] == "interval"
            assert poll_prices_call.kwargs["hours"] == 6
            assert poll_prices_call.kwargs["args"] == [app.state.event_queue]
            assert "next_run_time" in poll_prices_call.kwargs

    scheduler.shutdown.assert_called_once_with(wait=False)
    finnhub.stop.assert_awaited_once()
    close_browser.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_requeues_pending_events_on_startup() -> None:
    app = SimpleNamespace(state=SimpleNamespace())

    db_result = MagicMock()
    db_scalars = MagicMock()
    db_scalars.all.return_value = [101, 202]
    db_result.scalars.return_value = db_scalars
    db_session = MagicMock()
    db_session.execute = AsyncMock(return_value=db_result)

    finnhub = MagicMock()
    finnhub.start = AsyncMock()
    finnhub.stop = AsyncMock()
    scheduler = MagicMock()

    with (
        patch("app.main.AsyncSessionLocal", return_value=_AsyncCM(db_session)),
        patch("app.main.FinnhubClient", return_value=finnhub),
        patch("app.main.AsyncIOScheduler", return_value=scheduler),
        patch("app.main.dispatcher.run", new=AsyncMock()),
    ):
        async with lifespan(app):
            queue = app.state.event_queue
            assert queue.get_nowait() == 101
            assert queue.get_nowait() == 202
            assert queue.empty()
