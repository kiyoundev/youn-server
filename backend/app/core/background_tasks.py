import asyncio
from collections.abc import Coroutine
from typing import Any

_background_tasks: set[asyncio.Task[None]] = set()


def spawn(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    """Fire-and-forget a coroutine while keeping a strong reference to its Task.

    asyncio.create_task()'s result must be held somewhere or it can be
    garbage-collected mid-run — this registry is that somewhere.
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
