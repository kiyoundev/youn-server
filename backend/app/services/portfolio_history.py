"""Portfolio value history
get_portfolio_history() derives [{date, value}] in CAD for a date range,
by replaying ledger prefixes through compute_positions rather than any new reconstruction logic."""

import asyncio
import logging
from bisect import bisect_right
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.services.fx import get_rate_history
from app.services.ledger_import import ledger_date
from app.services.positions import compute_positions
from app.services.stocks import DateRange, FinnhubClient, is_intraday_range
from app.services.wealthsimple_csv import LEDGER_TZ

_log = logging.getLogger(__name__)

PointKey = date | datetime

# Fixed day-counts, not calendar-month arithmetic — avoids month-overflow
# edge cases (e.g. Oct 31 minus 1 month) for a difference carry-forward
# would smooth over anyway. YTD and ALL are exact, not fuzzy windows.
_RANGE_TO_DAYS: dict[DateRange, int] = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
}


def _range_start(range_: DateRange, today: date, earliest: date) -> date:
    if range_ == "YTD":
        return date(today.year, 1, 1)
    if range_ == "ALL":
        return earliest  # earliest activity's date — no portfolio before it
    return today - timedelta(days=_RANGE_TO_DAYS[range_])


def _date_points(range_: DateRange, today: date, earliest: date) -> list[date]:
    """One date per calendar day (weekends/holidays included — carry-forward
    handles those) from range_start through today, inclusive. Never called
    for "1D": that range is intraday and reuses the price series' own
    timestamps as its x-axis instead (see get_portfolio_history)."""
    start = _range_start(range_, today, earliest)
    return [start + timedelta(days=i) for i in range((today - start).days + 1)]


def _price_series(raw: list[dict], parse_intraday: bool, collapse_to_date: bool) -> list[tuple[PointKey, float]]:
    """raw is get_price_history's own [{date, close}]. parse_intraday matches
    whichever string format that function actually wrote for this range
    (is_intraday_range's own interval-based decision) — not necessarily this
    function's own output granularity: 1W's bars are hourly (so
    timestamp-formatted) even though the portfolio chart wants one point per
    day for it. strptime with an explicit %z, not fromisoformat: fromisoformat's
    handling of that exact shape ("2026-10-29 09:30:00-04:00", space-separated,
    not fromisoformat's 'T') is version-dependent — works under 3.12, raises
    under 3.10 (the backend image's actual version) — where %z has reliably
    accepted a colon in the offset since 3.7.

    collapse_to_date additionally reduces a parsed intraday series down to one
    entry per calendar day, keeping each day's latest (chronologically last)
    bar — true for every range except 1D, whose own output keeps the full
    timestamp instead (see get_portfolio_history's point_keys)."""
    if parse_intraday:
        parsed = sorted((datetime.strptime(p["date"], "%Y-%m-%d %H:%M:%S%z"), p["close"]) for p in raw)
    else:
        parsed = sorted((date.fromisoformat(p["date"]), p["close"]) for p in raw)

    if not collapse_to_date:
        return parsed

    by_date: dict[date, float] = {}
    for key, price in parsed:  # ascending, so the last write per date wins
        by_date[key.date() if isinstance(key, datetime) else key] = price
    return sorted(by_date.items())


def _carry_forward(
    series: list[tuple[PointKey, float]], keys: list[PointKey], target: PointKey, backfill: bool = False
) -> float | None:
    """Latest price at or before target, or None if target is before every
    known point or the series is empty (the symbol never resolved at all).

    backfill (1D only): a held symbol missing before its own first reported
    bar — e.g. the 1D union's earliest timestamp predates this symbol's own
    first bar by a few minutes, a reporting-lag artifact, not "not bought
    yet" — uses that first known price instead of excluding it. Only sound
    for 1D, where holdings are provably constant all day (get_portfolio_history's
    is_1d); for every other range, a point before a symbol's first price
    could genuinely mean "not bought yet," so fabricating one there would be
    exactly the wrong kind of guess."""
    idx = bisect_right(keys, target) - 1
    if idx >= 0:
        return series[idx][1]
    return series[0][1] if backfill and series else None


def _total_deposits_cad(activities: list[Activity], through: date) -> float:
    """Cumulative net external cash in CAD, from the ledger's start through
    (and including) `through`. net_cash_amount is already CAD on every row
    (compute_positions relies on the same thing) — a USD trade's fx_rate is
    a separate column, not a currency on this one. MoneyMovement only, never
    Trade: buying a stock just moves money already in the account from cash
    to shares, it isn't new capital."""
    return sum(a.net_cash_amount for a in activities if a.activity_type == "MoneyMovement" and ledger_date(a.effective_at) <= through)


async def get_portfolio_history(db: AsyncSession, range_: DateRange, finnhub: FinnhubClient) -> list[dict]:
    # Raw query, not LedgerCache — that cache only remembers today's already-
    # collapsed result, not the day-by-day trail this function needs to
    # replay a different prefix of for every date point
    activities = (await db.execute(select(Activity))).scalars().all()
    if not activities:
        return []

    today = datetime.now(LEDGER_TZ).date()
    earliest = min(ledger_date(a.effective_at) for a in activities)
    is_1d = range_ == "1D"

    # Each date point's holdings+cash, via compute_positions on a
    # ledger prefix. 1D is one constant snapshot (today's full ledger) reused
    # for every intraday point — only price moves intraday, not share count.
    if is_1d:
        range_start = today
        holdings_by_point: dict[date, tuple[list, float]] = {today: compute_positions(activities)[:2]}
    else:
        range_start = _range_start(range_, today, earliest)
        holdings_by_point = {
            d: compute_positions([a for a in activities if ledger_date(a.effective_at) <= d])[:2]
            for d in _date_points(range_, today, earliest)
        }

    # Every (symbol, native_currency) pair held at any point in range.
    pairs = {(h.symbol, h.native_currency) for holdings, _cash in holdings_by_point.values() for h in holdings}

    # One get_price_history call per distinct pair, concurrent — not
    # per date point, same concurrency pattern as PriceService.get_prices.
    # parse_intraday matches get_price_history's own per-range decision
    # (true for 1D *and* 1W, since 1W's bars are hourly); collapse_to_date
    # is only false for 1D, whose own output wants the full timestamp.
    pairs = list(pairs)
    raw_histories = await asyncio.gather(*(finnhub.get_price_history(symbol, range_, currency) for symbol, currency in pairs))
    parse_intraday = is_intraday_range(range_)
    price_series = {
        pair: _price_series(raw, parse_intraday, collapse_to_date=not is_1d) for pair, raw in zip(pairs, raw_histories)
    }
    price_keys = {pair: [k for k, _ in series] for pair, series in price_series.items()}

    # One USD->CAD rate-history call, only if a held symbol needs it.
    fx_series: dict[date, float] = {}
    if any(currency == "USD" for _symbol, currency in pairs):
        fx_series = await get_rate_history(db, "USD", range_start, today)

    # 1D's canonical x-axis: the union of every held symbol's own fetched
    # timestamps (not an arbitrarily-chosen "first" symbol) — each symbol
    # still carry-forwards independently onto it, so a gap in one symbol's
    # series never distorts another's. Falls back to a single "today" point
    # if every fetch failed outright, so a ledger with cash but no priceable
    # holdings (or an upstream outage) still returns a value, not [].
    if is_1d:
        point_keys: list[PointKey] = sorted({k for series in price_series.values() for k, _ in series}) or [today]
    else:
        point_keys = sorted(holdings_by_point)

    # Second, independent figure per point: cumulative net external cash
    # (MoneyMovement only — a Trade just reallocates money already in the
    # account) from the ledger's earliest activity through this point. The
    # frontend's range %/$ change badge uses the *difference* between this
    # at its first and active points to strip deposits out of the raw value
    # diff, and the active point's own total as the % denominator — verified
    # against a real account's Wealthsimple-reported returns (deposits-so-far
    # as the denominator reproduces its % exactly; see issue #23 notes).
    # Trades never touch this, so a stock bought mid-range is already handled
    # correctly without any fixed-holdings backfill.
    if is_1d:
        deposits_by_point: dict[date, float] = {today: _total_deposits_cad(activities, today)}
    else:
        deposits_by_point = {d: _total_deposits_cad(activities, d) for d in _date_points(range_, today, earliest)}

    # Merge. value(point) = cash + sum(shares * price_in_cad). A
    # symbol with no resolvable price anywhere up to this point (a real fetch
    # failure, not a weekend gap — carry-forward already covers those) is
    # logged once and excluded from every point's sum, never counted as 0.
    excluded: set[tuple[str, str]] = set()
    result: list[dict] = []
    for key in point_keys:
        holdings, cash = holdings_by_point[today] if is_1d else holdings_by_point[key]
        total = cash
        for h in holdings:
            pair = (h.symbol, h.native_currency)
            price = _carry_forward(price_series[pair], price_keys[pair], key, backfill=is_1d)
            if price is None:
                if pair not in excluded:
                    _log.warning("No price data for %s (%s) anywhere in range %s — excluded", *pair, range_)
                    excluded.add(pair)
                continue
            if h.native_currency == "USD":
                rate = fx_series.get(key.date() if isinstance(key, datetime) else key)
                if rate is None:
                    continue  # fx.py already logs an unresolvable date; just skip this point's contribution
                price *= rate
            total += h.shares * price
        deposits = deposits_by_point[today] if is_1d else deposits_by_point[key]
        result.append({"date": str(key), "value": total, "total_deposits_cad": deposits})
    return result
