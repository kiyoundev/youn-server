from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

import app.services.fx as fx_module
from app.models.fx_rate import FxRate
from app.services.fx import fetch_fx_rates, refresh_fx_rates

_FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"


def _session(existing: dict[str, FxRate] | None = None) -> MagicMock:
    """MagicMock session, same convention as tests/scheduler/test_jobs.py
    and tests/api/test_items_routes.py — session.get(FxRate, currency)
    returns whatever row (if any) is preloaded for that currency."""
    rows = existing or {}
    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, currency: rows.get(currency))
    session.add = MagicMock(side_effect=lambda row: rows.__setitem__(row.currency, row))
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# fetch_fx_rates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_fetch_fx_rates_inverts_cad_based_response() -> None:
    # Real live-verified response shape (2026-08-20): base=CAD, rates are
    # CAD->X (how much foreign currency per 1 CAD) — must be inverted to
    # X->CAD for FxRate.rate_to_cad's contract.
    respx.get(_FRANKFURTER_URL, params={"base": "CAD", "symbols": "USD,KRW"}).mock(
        return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}})
    )
    rates = await fetch_fx_rates()
    assert rates is not None
    assert rates["USD"] == pytest.approx(1 / 0.7209)
    assert rates["KRW"] == pytest.approx(1 / 1003.11)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fx_rates_follows_redirect() -> None:
    # Regression (2026-08-20 live incident): api.frankfurter.app started
    # hard-redirecting (301) to api.frankfurter.dev, and httpx doesn't
    # follow redirects by default — this silently broke every scheduled
    # refresh_fx_rates_job run (raise_for_status() treats an unfollowed
    # 3xx as an error) until caught live. follow_redirects=True must
    # actually transparently succeed through a redirect hop, not just
    # avoid erroring on the primary (now-canonical) URL.
    old_host = "https://api.frankfurter.app/latest"
    respx.get(old_host).mock(return_value=httpx.Response(301, headers={"Location": _FRANKFURTER_URL}))
    respx.get(_FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}})
    )

    # Temporarily point fetch_fx_rates at the old (now-redirecting) host,
    # to prove follow_redirects=True actually transparently succeeds
    # through a redirect hop, not just "doesn't error against the current
    # canonical URL" (the other tests already cover that case).
    original_url = fx_module._FRANKFURTER_URL
    fx_module._FRANKFURTER_URL = old_host
    try:
        rates = await fetch_fx_rates()
    finally:
        fx_module._FRANKFURTER_URL = original_url

    assert rates is not None
    assert rates["USD"] == pytest.approx(1 / 0.7209)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fx_rates_non_200_returns_none() -> None:
    respx.get(_FRANKFURTER_URL).mock(return_value=httpx.Response(404, json={"message": "not found"}))
    assert await fetch_fx_rates() is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fx_rates_connection_error_returns_none() -> None:
    respx.get(_FRANKFURTER_URL).mock(side_effect=httpx.ConnectError("refused"))
    assert await fetch_fx_rates() is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_fx_rates_missing_currency_in_response_returns_none() -> None:
    # Malformed/partial upstream body — must not partially return, since
    # refresh_fx_rates treats None as "nothing to upsert" (all-or-nothing).
    respx.get(_FRANKFURTER_URL).mock(return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.72}}))
    assert await fetch_fx_rates() is None


# ---------------------------------------------------------------------------
# refresh_fx_rates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_refresh_fx_rates_upserts_both_rows() -> None:
    respx.get(_FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}})
    )
    session = _session()
    await refresh_fx_rates(session)

    added = {call.args[0].currency: call.args[0] for call in session.add.call_args_list}
    assert added["USD"].rate_to_cad == pytest.approx(1 / 0.7209)
    assert added["KRW"].rate_to_cad == pytest.approx(1 / 1003.11)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fx_rates_updates_existing_row_in_place() -> None:
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    existing = {
        "USD": FxRate(currency="USD", rate_to_cad=1.30, fetched_at=old_time),
        "KRW": FxRate(currency="KRW", rate_to_cad=0.0009, fetched_at=old_time),
    }
    session = _session(existing)

    respx.get(_FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}})
    )
    await refresh_fx_rates(session)

    # Same row objects mutated in place, not replaced — session.add() never
    # called again for a currency that already had a row.
    assert existing["USD"].rate_to_cad == pytest.approx(1 / 0.7209)
    assert existing["USD"].fetched_at > old_time
    session.add.assert_not_called()


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fx_rates_no_ops_on_fetch_failure() -> None:
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    existing = {"USD": FxRate(currency="USD", rate_to_cad=1.30, fetched_at=old_time)}
    session = _session(existing)

    respx.get(_FRANKFURTER_URL).mock(return_value=httpx.Response(500))
    await refresh_fx_rates(session)

    # Last-known rate stays in place — staleness is handled at read time
    # (GET /api/fx-rates), not write time.
    assert existing["USD"].rate_to_cad == 1.30
    assert existing["USD"].fetched_at == old_time
    session.commit.assert_not_awaited()
