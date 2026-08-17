import pytest

from app.core import background_tasks


@pytest.mark.asyncio
async def test_spawn_holds_and_releases_task_reference():
    async def _noop():
        return None

    task = background_tasks.spawn(_noop())
    assert task in background_tasks._background_tasks

    await task
    assert task not in background_tasks._background_tasks
