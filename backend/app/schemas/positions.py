from datetime import datetime
from typing import Literal

from pydantic import BaseModel

NativeCurrency = Literal["USD", "CAD"]
PriceStatus = Literal["ok", "stale", "unavailable", "currency_mismatch"]
AssetType = Literal["Stock", "ETF", "CDR"]


class PositionResponse(BaseModel):
    """One merged holding with its price (issue #19). GET /api/positions returns
    list[PositionResponse]; an empty ledger is []. Field-for-field with
    services.portfolio.PositionRow, so a row maps with PositionResponse(**asdict(row)).
    Money is in the holding's native currency, unrounded. Price-derived fields
    are None when the price is unavailable or withheld."""

    symbol: str
    native_currency: NativeCurrency
    shares: float
    avg_cost: float
    invested: float
    current_price: float | None
    price_status: PriceStatus
    price_as_of: datetime | None
    market_value: float | None
    unrealized_gain: float | None
    unrealized_gain_pct: float | None
    last_traded_at: datetime  # never null: a holding has at least one trade
    asset_type: AssetType | None  # None = unknown type or failed lookup: no badge
    allocation: float | None  # a fraction of the priced holdings' CAD value; None = unpriced or no USD rate


class CurrencySubtotal(BaseModel):
    """One currency's totals. invested covers every holding; market_value,
    unrealized_gain and unrealized_gain_pct cover priced holdings only, and the
    pct is against those holdings' cost, so an unpriced holding cannot make
    the rest look like a loss."""

    currency: NativeCurrency
    invested: float
    market_value: float
    unrealized_gain: float
    unrealized_gain_pct: float | None
    holdings_count: int
    unpriced_count: int


class PortfolioSummary(BaseModel):
    """GET /api/portfolio/summary. balance_cad = CAD market value + USD market
    value at today's fx_rates USD rate + cash; None when USD holdings exist but
    no USD rate does. unpriced_count > 0 makes the balance a lower bound."""

    subtotals: list[CurrencySubtotal]
    cash_cad: float
    balance_cad: float | None
    fx_available: bool
    fx_stale: bool
    unpriced_count: int
    invested_cad: float  # what the held shares cost in CAD at purchase-time rates, priced or not
