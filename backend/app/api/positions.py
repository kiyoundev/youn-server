"""Portfolio read routes (issue #19). Holdings are derived from the Activity
ledger (#33) and priced on request; nothing here writes to Postgres. The
ledger comes from LedgerCache and prices from PriceService, so a 30s poll
costs no ledger query and at most one upstream call per symbol per 15s.
See .doc/diagrams/portfolio-page-flow-sequence.html."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.fx_rate import FxRate
from app.schemas.positions import PortfolioSummary, PositionResponse
from app.services.fx import STALE_THRESHOLD_HOURS
from app.services.ledger_cache import LedgerCache, LedgerSnapshot
from app.services.ledger_errors import LedgerImportError
from app.services.portfolio import PositionRow, build_rows, build_summary
from app.services.prices import PriceService

router = APIRouter()


def get_ledger_cache(request: Request) -> LedgerCache:
    return request.app.state.ledger_cache


def get_price_service(request: Request) -> PriceService:
    return request.app.state.prices


async def _load_snapshot(ledger: LedgerCache, db: AsyncSession) -> LedgerSnapshot:
    """The ledger passed the integrity checks when it was imported, so
    LedgerImportError here means the stored rows were changed behind the
    app's back. That is a server fault, not a bad request: 500 with the
    error's code and message, rather than an unhandled crash."""
    try:
        return await ledger.get(db)
    except LedgerImportError as e:
        raise HTTPException(status_code=500, detail={"code": e.code, "message": e.message}) from e


async def _load_priced_rows(
    ledger: LedgerCache, prices: PriceService, db: AsyncSession
) -> tuple[LedgerSnapshot, tuple[PositionRow, ...]]:
    """What both routes start from: the ledger snapshot and its holdings
    joined with their quotes, already sorted. Both come from caches, so the
    second route of a page load costs no query and no upstream call."""
    snapshot = await _load_snapshot(ledger, db)
    quotes = await prices.get_prices({(h.symbol, h.native_currency) for h in snapshot.holdings})
    return snapshot, build_rows(snapshot.holdings, quotes)


@router.get(
    "/api/positions",
    response_model=list[PositionResponse],
    summary="Get portfolio holdings with current prices",
    description=(
        "One row per (symbol, native currency), merged across accounts, "
        "sorted by market value descending with unpriced rows last. Money is "
        "in the holding's native currency. A row with no usable price still "
        "appears, with price_status explaining why and the price-derived "
        "fields null. An empty ledger is []."
    ),
)
async def get_positions(
    db: AsyncSession = Depends(get_db),
    ledger: LedgerCache = Depends(get_ledger_cache),
    prices: PriceService = Depends(get_price_service),
) -> list[PositionResponse]:
    _, rows = await _load_priced_rows(ledger, prices, db)
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
        "the balance leaves those holdings out."
    ),
)
async def get_portfolio_summary(
    db: AsyncSession = Depends(get_db),
    ledger: LedgerCache = Depends(get_ledger_cache),
    prices: PriceService = Depends(get_price_service),
) -> PortfolioSummary:
    snapshot, rows = await _load_priced_rows(ledger, prices, db)

    usd = await db.get(FxRate, "USD")  # primary key lookup; None before the first refresh
    rate = usd.rate_to_cad if usd else None
    stale = usd is not None and usd.fetched_at < datetime.now(timezone.utc) - timedelta(hours=STALE_THRESHOLD_HOURS)

    return PortfolioSummary(**asdict(build_summary(rows, snapshot.cash, rate, stale)))
