from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.scheduler.jobs import poll_prices, poll_stocks

router = APIRouter()

_RATE_LIMIT_WINDOW = timedelta(minutes=5)
_last_prices_trigger: datetime | None = None
_last_stocks_trigger: datetime | None = None


def _check_rate_limit(last_trigger: datetime | None) -> None:
    if last_trigger is None:
        return
    elapsed = datetime.now(timezone.utc) - last_trigger
    if elapsed < _RATE_LIMIT_WINDOW:
        remaining = int((_RATE_LIMIT_WINDOW - elapsed).total_seconds())
        raise HTTPException(status_code=429, detail=f"Rate limited, try again in {remaining}s")


@router.post("/api/poll/prices")
async def trigger_poll_prices(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    global _last_prices_trigger
    _check_rate_limit(_last_prices_trigger)
    _last_prices_trigger = datetime.now(timezone.utc)
    background_tasks.add_task(poll_prices, request.app.state.event_queue)
    return {"status": "queued"}


@router.post("/api/poll/stocks")
async def trigger_poll_stocks(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    global _last_stocks_trigger
    _check_rate_limit(_last_stocks_trigger)
    _last_stocks_trigger = datetime.now(timezone.utc)
    background_tasks.add_task(poll_stocks, request.app.state.finnhub)
    return {"status": "queued"}
