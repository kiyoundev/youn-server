import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.api import poll


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    poll._last_prices_trigger = None
    poll._last_stocks_trigger = None
    yield
    poll._last_prices_trigger = None
    poll._last_stocks_trigger = None


@pytest.mark.asyncio
async def test_trigger_poll_prices_enqueues_background_task() -> None:
    app = FastAPI()
    queue = asyncio.Queue()
    app.state.event_queue = queue

    request = SimpleNamespace(app=app)
    background_tasks = BackgroundTasks()

    with patch("app.api.poll.poll_prices", new=AsyncMock()) as poll_fn:
        response = await poll.trigger_poll_prices(request, background_tasks)

    assert response == {"status": "queued"}
    assert len(background_tasks.tasks) == 1

    task = background_tasks.tasks[0]
    assert task.func is poll_fn
    assert task.args == (queue,)
    assert task.kwargs == {}


@pytest.mark.asyncio
async def test_trigger_poll_prices_rate_limited_within_5_minutes() -> None:
    app = FastAPI()
    app.state.event_queue = asyncio.Queue()
    request = SimpleNamespace(app=app)

    with patch("app.api.poll.poll_prices", new=AsyncMock()):
        await poll.trigger_poll_prices(request, BackgroundTasks())

        with pytest.raises(HTTPException) as exc_info:
            await poll.trigger_poll_prices(request, BackgroundTasks())

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_trigger_poll_prices_allowed_after_window_elapses() -> None:
    app = FastAPI()
    app.state.event_queue = asyncio.Queue()
    request = SimpleNamespace(app=app)

    poll._last_prices_trigger = datetime.now(timezone.utc) - timedelta(minutes=6)

    with patch("app.api.poll.poll_prices", new=AsyncMock()):
        response = await poll.trigger_poll_prices(request, BackgroundTasks())

    assert response == {"status": "queued"}


@pytest.mark.asyncio
async def test_trigger_poll_stocks_enqueues_background_task() -> None:
    app = FastAPI()
    finnhub = SimpleNamespace()
    app.state.finnhub = finnhub

    request = SimpleNamespace(app=app)
    background_tasks = BackgroundTasks()

    with patch("app.api.poll.poll_stocks", new=AsyncMock()) as poll_fn:
        response = await poll.trigger_poll_stocks(request, background_tasks)

    assert response == {"status": "queued"}
    assert len(background_tasks.tasks) == 1

    task = background_tasks.tasks[0]
    assert task.func is poll_fn
    assert task.args == (finnhub,)


@pytest.mark.asyncio
async def test_trigger_poll_stocks_rate_limited_within_5_minutes() -> None:
    app = FastAPI()
    app.state.finnhub = SimpleNamespace()
    request = SimpleNamespace(app=app)

    with patch("app.api.poll.poll_stocks", new=AsyncMock()):
        await poll.trigger_poll_stocks(request, BackgroundTasks())

        with pytest.raises(HTTPException) as exc_info:
            await poll.trigger_poll_stocks(request, BackgroundTasks())

    assert exc_info.value.status_code == 429


def test_prices_and_stocks_rate_limits_are_independent() -> None:
    poll._last_prices_trigger = datetime.now(timezone.utc)
    poll._check_rate_limit(poll._last_stocks_trigger)  # should not raise — stocks untouched
