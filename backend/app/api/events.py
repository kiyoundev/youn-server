"""SSE streaming route — long-lived GET /api/events/stream connection.

Wraps `app.services.sse`'s in-memory fan-out: each connection registers its
own mailbox on connect, drains it for the life of the connection, and
unregisters on disconnect/cancellation.
"""

import asyncio
import logging

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.services import sse

_log = logging.getLogger(__name__)

router = APIRouter()

_PING_INTERVAL = 15  # seconds — idle ceiling before sending a keepalive ping


async def _event_generator():
    # register() creates this connection's own mailbox and adds it to sse.py's
    # shared fan-out set — from this point on, broadcast() can reach it.
    queue = sse.register()
    try:
        while True:
            try:
                # Block here until either a real event lands in our mailbox,
                # or _PING_INTERVAL seconds pass with nothing arriving —
                # whichever happens first. This is the connection's only
                # await point while idle, so it's also where a disconnect
                # gets noticed (see the `finally` note below).
                data = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                # Nothing broadcast within the window — the normal, expected
                # case (scrapes are ~6h apart). Send a no-op SSE comment
                # instead of silently waiting again. This isn't just a
                # keepalive: writing something is what gives the OS a chance
                # to notice a dead connection. A connection that's gone
                # silent (wifi drop, no clean FIN ever sent) looks identical
                # to a healthy idle one from a purely passive check — only
                # attempting a real write can eventually surface the failure.
                yield ": ping\n\n"
    finally:
        # Runs on ANY exit from this generator — clean disconnect, a failed
        # ping write, or server shutdown. Starlette tears this generator down
        # by throwing GeneratorExit in at whatever `yield` it's paused on,
        # which is a BaseException, not an Exception — deliberately not
        # caught above with `except Exception`, since that wouldn't catch it
        # anyway. `finally` runs regardless of exception type, so no
        # explicit `except` clause is needed to guarantee this cleanup.
        sse.unregister(queue)


@router.get(
    "/api/events/stream",
    summary="Live listing-change stream (SSE)",
    description=(
        "Long-lived Server-Sent Events connection. Pushes "
        '`{"product_id": <int>, "listing_id": <int>}` on every successful '
        "scrape, regardless of price change. In-memory only — a missed "
        "push is corrected by the client's own reconnect/refetch, not by "
        "server-side replay."
    ),
)
async def stream_events() -> StreamingResponse:
    """Open an SSE connection and stream listing-changed events as they occur.

    Returns:
        A `StreamingResponse` with `media_type="text/event-stream"` that
        stays open until the client disconnects (detected via a failed
        keepalive ping write, not a passive disconnect check — see
        `_event_generator`).
    """
    return StreamingResponse(_event_generator(), media_type="text/event-stream")
