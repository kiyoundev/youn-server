"""Portfolio read routes (issue #19). Holdings are derived from the Activity
ledger (#33) and priced on request; nothing here writes to Postgres. The
ledger comes from LedgerCache and prices from PriceService, so a 30s poll
costs no ledger query and at most one upstream call per symbol per 15s.
Only /positions also asks AssetTypeService for each row's badge.
See .doc/diagrams/portfolio-page-flow-sequence.html."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_ledger_cache
from app.models.fx_rate import FxRate
from app.schemas.positions import PortfolioSummary, PositionResponse
from app.services.asset_types import AssetTypeService
from app.services.fx import STALE_THRESHOLD_HOURS
from app.services.ledger_cache import LedgerCache, LedgerSnapshot
from app.services.ledger_errors import LedgerImportError
from app.services.portfolio import PositionRow, build_rows, build_summary
from app.services.prices import PriceService

router = APIRouter()


def get_price_service(request: Request) -> PriceService:
    return request.app.state.prices


def get_asset_type_service(request: Request) -> AssetTypeService:
    return request.app.state.asset_types


async def _load_snapshot(ledger: LedgerCache, db: AsyncSession) -> LedgerSnapshot:
    """The ledger passed the integrity checks when it was imported, so
    LedgerImportError here means the stored rows were changed behind the
    app's back. That is a server fault, not a bad request: 500 with the
    error's code and message, rather than an unhandled crash."""
    try:
        return await ledger.get(db)
    except LedgerImportError as e:
        raise HTTPException(status_code=500, detail={"code": e.code, "message": e.message}) from e


async def _load_usd_rate(db: AsyncSession) -> tuple[float | None, bool]:
    """Today's USD->CAD rate from fx_rates and whether it is over 24h old.
    A primary-key lookup; None before the first refresh."""
    usd = await db.get(FxRate, "USD")
    if usd is None:
        return None, False
    stale = usd.fetched_at < datetime.now(timezone.utc) - timedelta(hours=STALE_THRESHOLD_HOURS)
    return usd.rate_to_cad, stale


async def _load_priced_rows(
    ledger: LedgerCache, prices: PriceService, db: AsyncSession, types: AssetTypeService | None = None
) -> tuple[LedgerSnapshot, tuple[PositionRow, ...], tuple[float | None, bool]]:
    """What both routes start from: the ledger snapshot, its holdings joined
    with their quotes (already sorted), and the USD rate as (rate, stale). The
    rate is read once here because allocation needs it and the summary needs it
    for the balance. All three come from caches or a key lookup, so the second
    route of a page load costs no ledger query and no upstream call.

    Pass `types` to also fill each row's asset_type; the lookups run alongside
    the price fetches, so a first call takes as long as the slower of the two.
    Without it every asset_type is None, which is what the summary wants: it
    never shows a badge, so it must not wait on one."""
    snapshot = await _load_snapshot(ledger, db)
    usd_rate, usd_stale = await _load_usd_rate(db)
    # Both reads are done and the results are plain values. End the read
    # transaction so the pooled connection goes back now, not after the
    # upstream waits below: a slow Yahoo or Finnhub would otherwise leave it
    # idle for the whole wait, on every request.
    await db.rollback()
    pairs = {(h.symbol, h.native_currency) for h in snapshot.holdings}
    if types is None:
        quotes, asset_types = await prices.get_prices(pairs), {}
    else:
        quotes, asset_types = await asyncio.gather(prices.get_prices(pairs), types.get_types(pairs))
    rows = build_rows(snapshot.holdings, quotes, asset_types, usd_rate)
    return snapshot, rows, (usd_rate, usd_stale)


@router.get(
    "/api/positions",
    response_model=list[PositionResponse],
    summary="Get portfolio holdings with current prices",
    description=(
        "One row per (symbol, native currency), merged across accounts, "
        "sorted by value descending with unpriced rows last. Money is "
        "in the holding's native currency. A row with no usable price still "
        "appears, with price_status explaining why and the price-derived "
        "fields null. asset_type is Stock, ETF or CDR, or null when the type "
        "is unknown; it never affects the price fields. allocation is the "
        "row's share of the priced holdings' total value in CAD (USD at "
        "today's fx_rates rate), a fraction, or null when the row is unpriced "
        "or the USD rate is missing. Rows are sorted largest first by that "
        "CAD value. An empty ledger is []."
    ),
)
async def get_positions(
    db: AsyncSession = Depends(get_db),
    ledger: LedgerCache = Depends(get_ledger_cache),
    prices: PriceService = Depends(get_price_service),
    types: AssetTypeService = Depends(get_asset_type_service),
) -> list[PositionResponse]:
    _, rows, _ = await _load_priced_rows(ledger, prices, db, types)
    return [PositionResponse(**asdict(row)) for row in rows]


@router.get(
    "/api/portfolio/summary",
    response_model=PortfolioSummary,
    summary="Get portfolio totals and CAD balance",
    description=(
        "Per-currency subtotals (USD, CAD) of invested, market value and "
        "unrealized gain, plus cash and the account balance in CAD. The "
        "balance converts USD at today's fx_rates USD rate and is null when "
        "a priced USD holding exists but no rate does (fx_available false). "
        "fx_stale means that rate is over 24h old. unpriced_count > 0 means "
        "the balance leaves those holdings out. invested_cad is what the held "
        "shares cost in CAD at the rates of the days they were bought, "
        "whether or not they are priced."
    ),
)
async def get_portfolio_summary(
    db: AsyncSession = Depends(get_db),
    ledger: LedgerCache = Depends(get_ledger_cache),
    prices: PriceService = Depends(get_price_service),
) -> PortfolioSummary:
    snapshot, rows, (rate, stale) = await _load_priced_rows(ledger, prices, db)
    return PortfolioSummary(**asdict(build_summary(rows, snapshot.cash, rate, stale, snapshot.invested_cad)))
