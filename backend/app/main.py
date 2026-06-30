import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.scheduler.jobs import poll_prices
from app.services.stocks import FinnhubClient

_TZ = ZoneInfo("America/Toronto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue: asyncio.Queue = asyncio.Queue()

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

    app.state.event_queue = queue
    app.state.finnhub = finnhub
    app.state.scheduler = scheduler

    yield

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
