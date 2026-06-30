import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.consumers import dispatcher
from app.core.db import AsyncSessionLocal, get_db
from app.models.event import Event
from app.scheduler.jobs import poll_prices
from app.services.stocks import FinnhubClient

_log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Toronto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue: asyncio.Queue[int] = asyncio.Queue()

    # crash recovery: reload unprocessed events from the previous run
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Event.id).where(Event.status == "pending")
        )
        pending_ids: list[int] = result.scalars().all()
    for event_id in pending_ids:
        await queue.put(event_id)
    if pending_ids:
        _log.info("lifespan: requeued %d pending event(s) from DB", len(pending_ids))

    finnhub = FinnhubClient(event_queue=queue)
    await finnhub.start()

    scheduler = AsyncIOScheduler(timezone=_TZ)
    scheduler.add_job(
        poll_prices,
        "interval",
        hours=6,
        args=[queue],
        next_run_time=datetime.now(_TZ),
    )
    scheduler.start()

    dispatch_task = asyncio.create_task(dispatcher.run(queue))

    app.state.event_queue = queue
    app.state.finnhub = finnhub
    app.state.scheduler = scheduler
    app.state.dispatch_task = dispatch_task

    yield

    dispatch_task.cancel()
    await asyncio.gather(dispatch_task, return_exceptions=True)
    scheduler.shutdown(wait=False)
    await finnhub.stop()


app = FastAPI(title="youn-server", lifespan=lifespan)


@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    return {"status": "ok"}


@app.post("/api/poll/prices")
async def trigger_poll(request: Request, background_tasks: BackgroundTasks):
    # No auth yet (Issue #8) and no concurrency guard — hitting this while the
    # scheduler job is running starts two concurrent scrape cycles.
    background_tasks.add_task(poll_prices, request.app.state.event_queue)
    return {"status": "triggered"}
