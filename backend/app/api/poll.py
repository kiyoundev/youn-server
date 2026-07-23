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


@router.post(
    "/api/poll/prices",
    summary="Manually trigger a wishlist price poll cycle",
    description=(
        "Rate-limited to one call per 5 minutes. Runs as a background task — "
        "returns immediately with `status='queued'` rather than waiting for "
        "the scrape cycle to finish."
    ),
)
async def trigger_poll_prices(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Manually trigger the wishlist price-poll job outside its normal 6h schedule.

    Args:
        request: Used to reach the shared `event_queue` on `app.state`.
        background_tasks: FastAPI's background-task runner.

    Returns:
        `{"status": "queued"}`.

    Raises:
        HTTPException: 429 if called again within 5 minutes of the last trigger.
    """
    global _last_prices_trigger
    _check_rate_limit(_last_prices_trigger)
    _last_prices_trigger = datetime.now(timezone.utc)
    background_tasks.add_task(poll_prices, request.app.state.event_queue)
    return {"status": "queued"}


@router.post(
    "/api/poll/stocks",
    summary="Manually trigger a stock threshold poll cycle",
    description=(
        "Rate-limited to one call per 5 minutes. Runs as a background task — "
        "returns immediately with `status='queued'`."
    ),
)
async def trigger_poll_stocks(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Manually trigger a one-off stock-threshold check outside the live feed.

    Args:
        request: Used to reach the shared `FinnhubClient` on `app.state`.
        background_tasks: FastAPI's background-task runner.

    Returns:
        `{"status": "queued"}`.

    Raises:
        HTTPException: 429 if called again within 5 minutes of the last trigger.
    """
    global _last_stocks_trigger
    _check_rate_limit(_last_stocks_trigger)
    _last_stocks_trigger = datetime.now(timezone.utc)
    background_tasks.add_task(poll_stocks, request.app.state.finnhub)
    return {"status": "queued"}
