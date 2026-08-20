import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import analysis, events, fx, health, items, poll, stock_alerts, system
from app.consumers import dispatcher
from app.core.auth import verify_api_key
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.models.event import Event
from app.scheduler.jobs import poll_prices, refresh_fx_rates_job
from app.services.scraper.patchright_scraper import PatchrightScraper
from app.services.stocks import FinnhubClient
from app.services.synology import synology_client

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Toronto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue: asyncio.Queue[int] = asyncio.Queue()

    # crash recovery: reload unprocessed events from the previous run
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Event.id).where(Event.status == "pending"))
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
    # Issue #45 — same "interval" + immediate next_run_time pattern as
    # poll_prices above: fires once at boot, then every 24h from that boot
    # time, not anchored to midnight (see jobs.refresh_fx_rates_job).
    scheduler.add_job(
        refresh_fx_rates_job,
        "interval",
        hours=24,
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
    await synology_client.close()
    await PatchrightScraper.close_browser()  # no-op if never launched (lazy init)
    await PatchrightScraper.stop_xvfb()  # no-op if never launched (lazy init) — #15


app = FastAPI(title="youn-server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(events.router, dependencies=[Depends(verify_api_key)])
app.include_router(items.router, dependencies=[Depends(verify_api_key)])
app.include_router(stock_alerts.router, dependencies=[Depends(verify_api_key)])
app.include_router(poll.router, dependencies=[Depends(verify_api_key)])
app.include_router(analysis.router, dependencies=[Depends(verify_api_key)])
app.include_router(system.router, dependencies=[Depends(verify_api_key)])
app.include_router(fx.router, dependencies=[Depends(verify_api_key)])
