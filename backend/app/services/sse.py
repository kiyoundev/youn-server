"""In-memory fan-out for Server-Sent Events.

One `asyncio.Queue` per open `/api/events/stream` connection. `broadcast()`
drops a copy of the payload into every currently-registered queue; each
connection's own streaming generator drains its queue independently. Not
DB-backed — a missed push just means the next reconnect re-syncs via a
normal fetch (see `.plan/36-wishlist-page-real-data-sse/schema.md`).
"""

import asyncio
import json
import logging

_log = logging.getLogger(__name__)

_clients: set[asyncio.Queue[str]] = set()


def register() -> asyncio.Queue[str]:
    """Open a new mailbox and add it to the fan-out set. Call once per connection."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    _clients.add(queue)
    _log.debug("sse: client registered (%d total)", len(_clients))
    return queue


def unregister(queue: asyncio.Queue[str]) -> None:
    """Remove a mailbox from the fan-out set. Safe to call even if already removed."""
    _clients.discard(queue)
    _log.debug("sse: client unregistered (%d total)", len(_clients))


def broadcast(payload: dict) -> None:
    """Serialize `payload` once and drop a copy into every registered mailbox."""
    if not _clients:
        return
    data = json.dumps(payload)
    for queue in _clients:
        queue.put_nowait(data)
