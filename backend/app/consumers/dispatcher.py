import asyncio
import logging
from datetime import datetime, timezone

from app.consumers import analysis, notify
from app.core.db import AsyncSessionLocal
from app.models.event import Event

_log = logging.getLogger(__name__)


async def run(queue: asyncio.Queue[int]) -> None:
    _log.info("event dispatcher started")
    while True:
        event_id: int = await queue.get()
        try:
            await _dispatch(event_id)
        except Exception:
            _log.error("dispatcher: unhandled error for event %d", event_id, exc_info=True)
        finally:
            queue.task_done()


async def _dispatch(event_id: int) -> None:
    now = datetime.now(timezone.utc)

    # Phase 1: fetch event and send notification (read-only session, no commit needed)
    async with AsyncSessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None:
            _log.warning("dispatcher: event %d not found in DB", event_id)
            return

        try:
            await notify.handle(event, session)
        except Exception:
            _log.error(
                "dispatcher: notify failed for event %d (%s)",
                event_id,
                event.type,
                exc_info=True,
            )
            event.status = "failed"
            await session.commit()
            return
    # session 1 closed; event attributes still readable (expire_on_commit=False)

    # Phase 2: analysis in its own session — failure cannot poison the status commit
    if event.type == "STOCK_THRESHOLD":
        async with AsyncSessionLocal() as analysis_session:
            try:
                await analysis.handle(event, analysis_session)
                await analysis_session.commit()
            except Exception:
                _log.error(
                    "dispatcher: analysis stub failed for event %d", event_id, exc_info=True
                )

    # Phase 3: mark processed in a clean session, guaranteed not poisoned by phases 1–2
    async with AsyncSessionLocal() as status_session:
        ev = await status_session.get(Event, event_id)
        if ev:
            ev.status = "processed"
            ev.processed_at = now
            await status_session.commit()
