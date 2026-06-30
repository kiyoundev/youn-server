from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import lifespan


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_scheduler_and_finnhub() -> None:
    app = SimpleNamespace(state=SimpleNamespace())

    finnhub = MagicMock()
    finnhub.start = AsyncMock()
    finnhub.stop = AsyncMock()

    scheduler = MagicMock()

    with (
        patch("app.main.FinnhubClient", return_value=finnhub) as finnhub_cls,
        patch("app.main.AsyncIOScheduler", return_value=scheduler) as scheduler_cls,
    ):
        async with lifespan(app):
            finnhub.start.assert_awaited_once()
            scheduler.start.assert_called_once()

            assert hasattr(app.state, "event_queue")
            assert app.state.finnhub is finnhub
            assert app.state.scheduler is scheduler

            finnhub_cls.assert_called_once_with(event_queue=app.state.event_queue)
            scheduler_cls.assert_called_once()

            add_job_call = scheduler.add_job.call_args
            assert add_job_call.args[1] == "interval"
            assert add_job_call.kwargs["hours"] == 6
            assert add_job_call.kwargs["args"] == [app.state.event_queue]
            assert "next_run_time" in add_job_call.kwargs

    scheduler.shutdown.assert_called_once_with(wait=False)
    finnhub.stop.assert_awaited_once()
