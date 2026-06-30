import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI

from app.main import trigger_poll


@pytest.mark.asyncio
async def test_trigger_poll_enqueues_background_price_poll() -> None:
    app = FastAPI()
    queue = asyncio.Queue()
    app.state.event_queue = queue

    request = SimpleNamespace(app=app)
    background_tasks = BackgroundTasks()

    async def fake_poll_prices(_queue):
        return None

    with patch("app.main.poll_prices", new=AsyncMock(side_effect=fake_poll_prices)) as poll_fn:
        response = await trigger_poll(request, background_tasks)

    assert response == {"status": "triggered"}
    assert len(background_tasks.tasks) == 1

    task = background_tasks.tasks[0]
    assert task.func is poll_fn
    assert task.args == (queue,)
    assert task.kwargs == {}
