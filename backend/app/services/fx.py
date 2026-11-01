import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fx_rate import FxRate
from app.models.fx_rate_history import FxRateHistory

_log = logging.getLogger(__name__)

_FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"
_FRANKFURTER_URL = f"{_FRANKFURTER_BASE_URL}/latest"
_FX_TIMEOUT_SECONDS = 10
# Issue #45 — the only two non-CAD currencies this app supports.
FOREIGN_CURRENCIES = ("USD", "KRW")
# GET /api/fx-rates (api/fx.py) reports stale=True past this age — kept
# alongside the fetch logic since it's conceptually "how fresh does a rate
# from this source need to be," not a display-layer concern.
STALE_THRESHOLD_HOURS = 24
# Issue #74 — how far before a requested range's start get_rate_history()
# looks for an already-known rate to carry forward into a gap sitting right
# at the start of the range (e.g. the range starts on a Saturday). Wide
# enough for any real holiday cluster; doesn't trigger a fetch on its own,
# only used opportunistically against whatever's already cached.
_CARRY_FORWARD_LOOKBACK_DAYS = 10


async def fetch_fx_rates() -> dict[str, float] | None:
    """One request, CAD as base: GET /v1/latest?base=CAD&symbols=USD,KRW.

    Host is api.frankfurter.dev, not api.frankfurter.app — the .app domain
    started hard-redirecting here (301) as of 2026-08-20, breaking every
    scheduled refresh_fx_rates_job run silently (httpx doesn't follow
    redirects by default, and raise_for_status() treats an unfollowed 3xx
    as an error) until caught live. follow_redirects=True below is
    defensive against this happening again the same way, not a substitute
    for pointing at the right host.

    Verified live (2026-08-20) that `from`/`base` accepts a single currency
    only — `from=USD,KRW` 404s ("not found"). `to`/`symbols` is the side
    that takes a CSV list, so getting both rates in one request means using
    CAD as the base and inverting: the raw response is CAD→X (how much
    foreign currency per 1 CAD), but FxRate.rate_to_cad needs X→CAD (1 unit
    of the foreign currency in CAD).

    Returns {"USD": rate, "KRW": rate}, each already inverted, or None on
    any failure (network, non-200, malformed body, missing currency) —
    callers treat None as "nothing to upsert," never partially write.
    """
    try:
        # follow_redirects=True is defensive, not load-bearing — this exact
        # class of bug (frankfurter.app -> frankfurter.dev, a full domain
        # migration, discovered live 2026-08-20 breaking every scheduled
        # refresh_fx_rates_job run silently) is cheap to guard against
        # happening again the same way.
        async with httpx.AsyncClient(timeout=_FX_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = await client.get(
                _FRANKFURTER_URL,
                params={"base": "CAD", "symbols": ",".join(FOREIGN_CURRENCIES)},
            )
        resp.raise_for_status()
        data = resp.json()
        raw_rates = data["rates"]
        return {currency: 1 / raw_rates[currency] for currency in FOREIGN_CURRENCIES}
    except Exception:
        _log.warning("fetch_fx_rates: request failed", exc_info=True)
        return None


async def refresh_fx_rates(session: AsyncSession) -> None:
    """Fetches + upserts both FxRate rows, and (issue #74) today's row in
    fx_rate_history for each currency — same fetch, same commit, so the
    live rate and the history table's "today" point never disagree. On
    fetch failure: logs (inside fetch_fx_rates) and returns without
    touching existing rows — last-known rate stays in place, staleness is
    handled at read time (GET /api/fx-rates), not write time."""
    rates = await fetch_fx_rates()
    if rates is None:
        return

    now = datetime.now(timezone.utc)
    today = now.date()
    for currency, rate_to_cad in rates.items():
        row = await session.get(FxRate, currency)
        if row is None:
            row = FxRate(currency=currency)
            session.add(row)
        row.rate_to_cad = rate_to_cad
        row.fetched_at = now

        history_row = await session.scalar(
            select(FxRateHistory).where(
                FxRateHistory.currency == currency, FxRateHistory.date == today
            )
        )
        if history_row is None:
            history_row = FxRateHistory(currency=currency, date=today)
            session.add(history_row)
        history_row.rate_to_cad = rate_to_cad
    await session.commit()
    _log.info("refresh_fx_rates: updated %s", list(rates.keys()))


async def _fetch_rate_range(currency: str, start: date, end: date) -> dict[date, float] | None:
    """One Frankfurter range request for [start, end]: GET
    /v1/{start}..{end}?base=CAD&symbols={currency}, inverted the same way
    fetch_fx_rates() is.

    Returns whatever dates Frankfurter actually has data for — a weekend or
    holiday is legitimately absent from a *successful* response, not an
    error, so the returned dict can be smaller than the requested span.
    Returns None on any request failure (network, non-200, malformed body)
    — distinct from an empty-but-successful dict, since get_rate_history()
    must never carry a rate forward across a date it was never able to even
    ask about."""
    url = f"{_FRANKFURTER_BASE_URL}/{start.isoformat()}..{end.isoformat()}"
    try:
        async with httpx.AsyncClient(timeout=_FX_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = await client.get(url, params={"base": "CAD", "symbols": currency})
        resp.raise_for_status()
        data = resp.json()
        return {
            date.fromisoformat(day): 1 / day_rates[currency]
            for day, day_rates in data["rates"].items()
            if currency in day_rates
        }
    except Exception:
        _log.warning(
            "_fetch_rate_range: request failed for %s %s..%s", currency, start, end, exc_info=True
        )
        return None


async def get_rate_history(
    session: AsyncSession, currency: str, start: date, end: date
) -> dict[date, float]:
    """Returns the USD→CAD rate for every resolvable date in [start, end]
    (issue #74) — the series a past portfolio-value chart needs, as
    opposed to FxRate's single live rate.

    Reads fx_rate_history first; fetches only whatever dates are missing
    from Frankfurter in one range call, persists them, then returns the
    combined series. A weekend/holiday gap (Frankfurter has nothing for a
    date, by design) is filled here at read time from the nearest earlier
    known rate — never written back as a duplicate row. A date whose fetch
    genuinely failed, or that's earlier than any known/available rate, is
    omitted from the result entirely — logged, never raised, never a
    fabricated or wrong rate. A caller (the portfolio-history chart) simply
    sees that date absent and connects across it, the same way a line
    chart already connects between every other pair of real points."""
    lookback_start = start - timedelta(days=_CARRY_FORWARD_LOOKBACK_DAYS)
    result = await session.execute(
        select(FxRateHistory).where(
            FxRateHistory.currency == currency,
            FxRateHistory.date >= lookback_start,
            FxRateHistory.date <= end,
        )
    )
    known: dict[date, float] = {row.date: row.rate_to_cad for row in result.scalars()}

    requested = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    missing = [d for d in requested if d not in known]

    fetch_failed_dates: set[date] = set()
    if missing:
        # min..max of a non-contiguous `missing` can re-cover already-known
        # dates sitting in between (e.g. Jan 1 and Jan 5 missing, Jan 2-4
        # already cached from an earlier request) — only add a row for a
        # date that's genuinely new, never re-add one already in `known`,
        # or the unique constraint on (currency, date) raises on commit.
        fetched = await _fetch_rate_range(currency, min(missing), max(missing))
        if fetched is None:
            fetch_failed_dates = set(missing)
        else:
            newly_fetched = {d: rate for d, rate in fetched.items() if d not in known}
            for d, rate in newly_fetched.items():
                session.add(FxRateHistory(currency=currency, date=d, rate_to_cad=rate))
                known[d] = rate
            if newly_fetched:
                await session.commit()

    last_known: float | None = None
    for d in sorted(d for d in known if d < start):
        last_known = known[d]

    series: dict[date, float] = {}
    for d in requested:
        if d in known:
            last_known = known[d]
            series[d] = last_known
        elif d not in fetch_failed_dates and last_known is not None:
            series[d] = last_known
        # else: unresolved — omitted, never a fabricated/wrong rate
    return series
