from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.fx_rate import FxRate
from app.schemas.fx import FxRatesResponse
from app.services.fx import FOREIGN_CURRENCIES, STALE_THRESHOLD_HOURS

router = APIRouter()


@router.get(
    "/api/fx-rates",
    response_model=FxRatesResponse,
    summary="Get cached FX rates",
    description=(
        "Read-only — served from the fx_rates table, refreshed daily by "
        "refresh_fx_rates_job. Never calls the upstream FX source inline, "
        "so a page load is never coupled to that service's uptime/latency."
    ),
)
async def get_fx_rates(db: AsyncSession = Depends(get_db)) -> FxRatesResponse:
    """Serve cached FX rates plus a staleness flag.

    Returns:
        `rates`: {"USD": rate, "KRW": rate} for whichever currencies have a
            row — legitimately `{}` before the first successful
            `refresh_fx_rates` run (empty-table bootstrap, not an error).
        `stale`: True if any of FOREIGN_CURRENCIES is missing a row
            entirely, or its `fetched_at` is older than
            STALE_THRESHOLD_HOURS.
        `fetched_at`: the *older* of the present rows' `fetched_at` values
            (the more-stale one determines trustworthiness), None if no
            rows exist yet.
    """
    result = await db.execute(select(FxRate))
    rows = {row.currency: row for row in result.scalars().all()}

    rates = {currency: row.rate_to_cad for currency, row in rows.items()}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STALE_THRESHOLD_HOURS)
    missing_any = any(currency not in rows for currency in FOREIGN_CURRENCIES)
    stale_any = any(row.fetched_at < cutoff for row in rows.values())
    stale = missing_any or stale_any

    fetched_at = min((row.fetched_at for row in rows.values()), default=None)

    return FxRatesResponse(rates=rates, stale=stale, fetched_at=fetched_at)
