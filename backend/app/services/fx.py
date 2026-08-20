import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fx_rate import FxRate

_log = logging.getLogger(__name__)

_FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
_FX_TIMEOUT_SECONDS = 10
# Issue #45 — the only two non-CAD currencies this app supports.
FOREIGN_CURRENCIES = ("USD", "KRW")
# GET /api/fx-rates (api/fx.py) reports stale=True past this age — kept
# alongside the fetch logic since it's conceptually "how fresh does a rate
# from this source need to be," not a display-layer concern.
STALE_THRESHOLD_HOURS = 24


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
    """Fetches + upserts both FxRate rows. On fetch failure: logs (inside
    fetch_fx_rates) and returns without touching existing rows — last-known
    rate stays in place, staleness is handled at read time (GET
    /api/fx-rates), not write time."""
    rates = await fetch_fx_rates()
    if rates is None:
        return

    now = datetime.now(timezone.utc)
    for currency, rate_to_cad in rates.items():
        row = await session.get(FxRate, currency)
        if row is None:
            row = FxRate(currency=currency)
            session.add(row)
        row.rate_to_cad = rate_to_cad
        row.fetched_at = now
    await session.commit()
    _log.info("refresh_fx_rates: updated %s", list(rates.keys()))
