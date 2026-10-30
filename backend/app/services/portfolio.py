"""Shapes the ledger's per-account holdings into the per-symbol rows the
portfolio page shows (issue #19). Pure — no DB, no FastAPI, no prices — so
it is cheap to test and safe to share between the two read routes."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from app.services.asset_types import AssetType
from app.services.positions import Holding
from app.services.prices import PriceQuote, PriceStatus


@dataclass(frozen=True)
class MergedHolding:
    """One symbol in one native currency, summed across every account that
    holds it. avg_cost is in that native currency and share-weighted."""

    symbol: str
    native_currency: Literal["CAD", "USD"]
    shares: float
    avg_cost: float
    last_traded_at: datetime  # latest across the accounts that hold it


def merge_holdings(holdings: Iterable[Holding]) -> tuple[MergedHolding, ...]:
    """Merge compute_positions' per-(account, symbol) holdings into one row per
    (symbol, native_currency).

    The currency is part of the key so the USD stock 'AVGO' and the CAD-native
    CDR 'AVGO' stay two rows — their costs are in different currencies and are
    never averaged together. Shares are summed; avg_cost is
    sum(shares * avg_cost_native) / sum(shares); last_traded_at is the latest
    of the accounts'. compute_positions already drops fully-sold holdings, so
    every input has shares > 0 and the division is safe. Output is sorted by
    (symbol, currency) so it is deterministic."""
    totals: dict[tuple[str, Literal["CAD", "USD"]], list[float]] = {}  # key -> [shares, cost]
    latest: dict[tuple[str, Literal["CAD", "USD"]], datetime] = {}
    for h in holdings:
        key = (h.symbol, h.native_currency)
        total = totals.setdefault(key, [0.0, 0.0])
        total[0] += h.shares
        total[1] += h.shares * h.avg_cost_native
        latest[key] = max(latest.get(key, h.last_traded_at), h.last_traded_at)

    return tuple(
        MergedHolding(symbol, currency, shares, cost / shares, latest[(symbol, currency)])
        for (symbol, currency), (shares, cost) in sorted(totals.items())
    )


@dataclass(frozen=True)
class PositionRow:
    """One table row: a merged holding joined with its price. Money fields are
    in the holding's native currency and unrounded. The price-derived fields
    are None when there is no usable price (unavailable / currency_mismatch).
    asset_type is None when the type is unknown or its lookup failed.
    allocation is the row's share of the priced holdings' total value in CAD,
    a fraction (0.2468 is 24.68%); None when the row is unpriced or the USD
    rate it needs is missing."""

    symbol: str
    native_currency: Literal["CAD", "USD"]
    shares: float
    avg_cost: float
    invested: float
    current_price: float | None
    price_status: PriceStatus
    price_as_of: datetime | None
    market_value: float | None
    unrealized_gain: float | None
    unrealized_gain_pct: float | None
    last_traded_at: datetime
    asset_type: AssetType | None
    allocation: float | None


def _build_row(h: MergedHolding, quote: PriceQuote | None, asset_type: AssetType | None) -> PositionRow:
    if quote is None:  # should not happen; never let it turn into a 500
        quote = PriceQuote(None, None, None, "unavailable")

    invested = h.shares * h.avg_cost
    market_value = gain = pct = None
    if quote.price is not None:  # ok and stale both carry a price
        market_value = h.shares * quote.price
        gain = market_value - invested
        pct = gain / invested if invested else None  # bonus shares: no cost basis

    return PositionRow(
        h.symbol, h.native_currency, h.shares, h.avg_cost, invested,
        quote.price, quote.status, quote.fetched_at,
        market_value, gain, pct, h.last_traded_at, asset_type, None,
    )


def _allocate(rows: Sequence[PositionRow], usd_rate: float | None) -> list[PositionRow]:
    """Fill in each priced row's allocation: its value in CAD over the priced
    holdings' total in CAD. USD is converted at usd_rate (today's rate, as for
    the balance), because a share of a mixed-currency total can't be taken in
    native units. Without a rate, a priced USD row can't be converted and
    neither can the total, so every allocation stays None; CAD-only holdings
    need no rate. Unpriced rows are left out of the total and stay None, so the
    percentages add up to 100 over what could be valued."""
    priced = [r for r in rows if r.market_value is not None]
    if usd_rate is None and any(r.native_currency == "USD" for r in priced):
        return list(rows)

    def cad(r: PositionRow) -> float:
        return r.market_value * (usd_rate if r.native_currency == "USD" else 1.0)

    total = sum(cad(r) for r in priced)
    if total <= 0:
        return list(rows)
    return [replace(r, allocation=cad(r) / total) if r.market_value is not None else r for r in rows]


def build_rows(
    holdings: Iterable[MergedHolding],
    quotes: Mapping[tuple[str, str], PriceQuote],
    asset_types: Mapping[tuple[str, str], AssetType | None],
    usd_rate: float | None = None,
) -> tuple[PositionRow, ...]:
    """Join merged holdings with their quotes and types and derive invested,
    market value, unrealized gain and allocation. A stale quote still has a
    price, so it is valued like a fresh one; a holding with no quote is treated
    as unavailable, and one with no type entry has asset_type None. Types never
    affect a price field. usd_rate (None = unknown) only feeds allocation.

    Sorted largest first, unpriced rows last, ties by symbol. "Largest" is the
    allocation when there is one, i.e. by value in CAD, so a USD and a CAD row
    compare fairly; without a rate it falls back to the native market value.
    Pure."""
    rows = []
    for h in holdings:
        key = (h.symbol, h.native_currency)
        rows.append(_build_row(h, quotes.get(key), asset_types.get(key)))
    rows = _allocate(rows, usd_rate)

    def size(r: PositionRow) -> float:
        return r.allocation if r.allocation is not None else (r.market_value or 0.0)

    return tuple(sorted(rows, key=lambda r: (r.market_value is None, -size(r), r.symbol, r.native_currency)))


@dataclass(frozen=True)
class CurrencyTotals:
    """One currency's totals. invested covers every holding; market_value and
    unrealized_gain cover priced holdings only, and the pct is against the
    priced holdings' own cost, so an unpriced holding cannot make the rest
    look like a loss. Mirrors schemas.positions.CurrencySubtotal."""

    currency: Literal["CAD", "USD"]
    invested: float
    market_value: float
    unrealized_gain: float
    unrealized_gain_pct: float | None
    holdings_count: int
    unpriced_count: int


@dataclass(frozen=True)
class SummaryData:
    """Mirrors schemas.positions.PortfolioSummary, so the route maps it with
    PortfolioSummary(**asdict(summary))."""

    subtotals: tuple[CurrencyTotals, ...]
    cash_cad: float
    balance_cad: float | None
    fx_available: bool
    fx_stale: bool
    unpriced_count: int
    invested_cad: float


def _totals(currency: Literal["CAD", "USD"], rows: Sequence[PositionRow]) -> CurrencyTotals:
    priced = [r for r in rows if r.current_price is not None]  # stale quotes count: they have a price
    priced_cost = sum(r.invested for r in priced)
    gain = sum(r.unrealized_gain for r in priced)
    return CurrencyTotals(
        currency=currency,
        invested=sum(r.invested for r in rows),
        market_value=sum(r.market_value for r in priced),
        unrealized_gain=gain,
        unrealized_gain_pct=gain / priced_cost if priced_cost else None,
        holdings_count=len(rows),
        unpriced_count=len(rows) - len(priced),
    )


def build_summary(
    rows: Iterable[PositionRow],
    cash: float,
    usd_rate: float | None,
    usd_rate_stale: bool,
    invested_cad: float,
) -> SummaryData:
    """Per-currency totals plus the CAD balance. Pure.

    invested_cad is what the held shares cost in CAD, at the rates of the days
    they were bought (the ledger's cash paid). It is passed in, not derived
    from rows, because the rows carry cost only in native currency.

    balance_cad = CAD market value + USD market value x usd_rate + cash, where
    usd_rate is today's USD->CAD rate (fx_rates), not the rate at each trade.
    Trade-time rates only feed cost, and no CAD gain is shown (#19 decision).

    The rate is needed only when at least one USD holding is priced. Without
    one, fx_available is True and fx_stale False whatever was passed in, so a
    missing or old rate never flags a number it did not touch. With a priced
    USD holding and no rate, balance_cad is None and fx_available False.
    Subtotals list USD first, then CAD, and only currencies that have holdings."""
    rows = list(rows)
    subtotals = tuple(
        _totals(currency, group)
        for currency in ("USD", "CAD")
        if (group := [r for r in rows if r.native_currency == currency])
    )
    by_currency = {t.currency: t for t in subtotals}
    cad_value = by_currency["CAD"].market_value if "CAD" in by_currency else 0.0
    usd = by_currency.get("USD")
    needs_rate = usd is not None and usd.holdings_count > usd.unpriced_count

    if not needs_rate:
        balance, available, stale = cad_value + cash, True, False
    elif usd_rate is None:
        balance, available, stale = None, False, False
    else:
        balance, available, stale = cad_value + usd.market_value * usd_rate + cash, True, usd_rate_stale

    return SummaryData(
        subtotals=subtotals,
        cash_cad=cash,
        balance_cad=balance,
        fx_available=available,
        fx_stale=stale,
        unpriced_count=sum(t.unpriced_count for t in subtotals),
        invested_cad=invested_cad,
    )
