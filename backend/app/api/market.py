"""Per-ticker price history; Ticker-scoped rather than nested under positions/stockalerts
a browsed-but-unheld ticker still has a price history, with no Position or StockAlert required to exist."""

from typing import Literal

from fastapi import APIRouter, Depends, Request

from app.schemas.market import MarketHistoryPoint
from app.services.stocks import DateRange, FinnhubClient

router = APIRouter()


def get_finnhub_client(request: Request) -> FinnhubClient:
    return request.app.state.finnhub


@router.get(
    "/api/market/{ticker}/history",
    response_model=list[MarketHistoryPoint],
    summary="Get a ticker's price history",
    description=(
        "One point per bar for the given range. date is a plain YYYY-MM-DD "
        "for daily+ ranges (1M/3M/6M/YTD/ALL), a full datetime for intraday "
        "ranges (1D/1W). native_currency resolves a CAD-native ticker through "
        "the same .TO suffix rule live quotes use; omitted or USD queries the "
        "bare ticker. Never raises on an upstream failure — [] instead, logged."
    ),
)
async def get_market_history(
    ticker: str,
    range: DateRange,
    native_currency: Literal["USD", "CAD"] | None = None,
    finnhub: FinnhubClient = Depends(get_finnhub_client),
) -> list[MarketHistoryPoint]:
    history = await finnhub.get_price_history(ticker, range, native_currency)
    return [MarketHistoryPoint(**point) for point in history]
