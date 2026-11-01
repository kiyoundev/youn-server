from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

import app.services.fx as fx_module
from app.models.fx_rate import FxRate
from app.models.fx_rate_history import FxRateHistory
from app.services.fx import fetch_fx_rates, get_rate_history, refresh_fx_rates

_FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
_FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


def _session(
    existing: dict[str, FxRate] | None = None,
    history_scalar_results: list[FxRateHistory | None] | None = None,
) -> MagicMock:
    """MagicMock session, same convention as tests/scheduler/test_jobs.py
    and tests/api/test_items_routes.py — session.get(FxRate, currency)
    returns whatever row (if any) is preloaded for that currency.

    session.add dispatches by type: an FxRate goes into `existing` (so a
    later session.get in the same test sees it, as before) — an
    FxRateHistory does not, since both models have a `.currency` attribute
    and would otherwise collide in one dict keyed by it.

    session.scalar (refresh_fx_rates's does-today's-history-row-already-
    exist check) is called once per currency in FOREIGN_CURRENCIES order
    (USD, then KRW) — `history_scalar_results` supplies what each call
    returns in that order, defaulting to [None, None] (no existing history
    row for either currency)."""
    rows = existing if existing is not None else {}

    def _add(row: object) -> None:
        if not isinstance(row, FxRateHistory):
            rows[row.currency] = row  # type: ignore[attr-defined]

    session = MagicMock()
    session.get = AsyncMock(side_effect=lambda model, currency: rows.get(currency))
    session.add = MagicMock(side_effect=_add)
    session.scalar = AsyncMock(side_effect=history_scalar_results or [None, None])
    session.commit = AsyncMock()
    return session


def _history_rows_result(rows: list[FxRateHistory]) -> MagicMock:
    """For get_rate_history's `select(FxRateHistory).where(...)` read, iterated
    directly via `.scalars()` (not `.scalars().all()`)."""
    result = MagicMock()
    result.scalars.return_value = rows
    return result


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

    added_fx_rates = {
        call.args[0].currency: call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], FxRate)
    }
    assert added_fx_rates["USD"].rate_to_cad == pytest.approx(1 / 0.7209)
    assert added_fx_rates["KRW"].rate_to_cad == pytest.approx(1 / 1003.11)
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

    # Same FxRate objects mutated in place, not replaced.
    assert existing["USD"].rate_to_cad == pytest.approx(1 / 0.7209)
    assert existing["USD"].fetched_at > old_time
    # This test's session has no pre-existing fx_rate_history rows, so the
    # dual-write (issue #74) does add two brand-new FxRateHistory rows —
    # the FxRate rows themselves are what must never be re-added.
    assert all(isinstance(call.args[0], FxRateHistory) for call in session.add.call_args_list)


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


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fx_rates_also_writes_todays_history_row() -> None:
    # Issue #74 — the dual-write: same fetch, same commit, so the live
    # rate and the history table's "today" point never disagree.
    respx.get(_FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}})
    )
    session = _session()
    await refresh_fx_rates(session)

    history_rows = {
        call.args[0].currency: call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], FxRateHistory)
    }
    assert history_rows["USD"].rate_to_cad == pytest.approx(1 / 0.7209)
    assert history_rows["USD"].date == datetime.now(timezone.utc).date()
    assert history_rows["KRW"].rate_to_cad == pytest.approx(1 / 1003.11)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fx_rates_updates_existing_history_row_in_place() -> None:
    # The scheduler's boot-anchored (not midnight-anchored) timing can
    # rerun this same day after a restart — must overwrite, never
    # duplicate (see .plan/74-usd-cad-rate-history/challenges.md #1).
    today = datetime.now(timezone.utc).date()
    existing_usd_history = FxRateHistory(currency="USD", date=today, rate_to_cad=1.30)
    existing_krw_history = FxRateHistory(currency="KRW", date=today, rate_to_cad=0.0009)
    session = _session(history_scalar_results=[existing_usd_history, existing_krw_history])

    respx.get(_FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, json={"base": "CAD", "rates": {"USD": 0.7209, "KRW": 1003.11}})
    )
    await refresh_fx_rates(session)

    assert existing_usd_history.rate_to_cad == pytest.approx(1 / 0.7209)
    assert existing_krw_history.rate_to_cad == pytest.approx(1 / 1003.11)
    # Mutated in place, never re-added.
    assert all(not isinstance(call.args[0], FxRateHistory) for call in session.add.call_args_list)


# ---------------------------------------------------------------------------
# get_rate_history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_rate_history_cache_hit_makes_no_frankfurter_call() -> None:
    d1, d2 = date(2026, 1, 5), date(2026, 1, 6)
    cached = [
        FxRateHistory(currency="USD", date=d1, rate_to_cad=1.40),
        FxRateHistory(currency="USD", date=d2, rate_to_cad=1.41),
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_history_rows_result(cached))
    session.add = MagicMock()
    session.commit = AsyncMock()

    # No respx route registered at all — respx raises if the code attempts
    # any HTTP request, which is exactly the assertion this test needs.
    series = await get_rate_history(session, "USD", d1, d2)

    assert series == {d1: 1.40, d2: 1.41}
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@respx.mock
async def test_get_rate_history_cache_miss_fetches_and_persists_missing_range() -> None:
    d1, d2, d3 = date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)
    session = MagicMock()
    session.execute = AsyncMock(return_value=_history_rows_result([]))
    session.add = MagicMock()
    session.commit = AsyncMock()

    respx.get(
        f"{_FRANKFURTER_BASE_URL}/{d1.isoformat()}..{d3.isoformat()}", params={"base": "CAD", "symbols": "USD"}
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "base": "CAD",
                "rates": {
                    "2026-01-05": {"USD": 0.7142},
                    "2026-01-06": {"USD": 0.7092},
                    "2026-01-07": {"USD": 0.7246},
                },
            },
        )
    )

    series = await get_rate_history(session, "USD", d1, d3)

    assert series[d1] == pytest.approx(1 / 0.7142)
    assert series[d2] == pytest.approx(1 / 0.7092)
    assert series[d3] == pytest.approx(1 / 0.7246)
    assert session.add.call_count == 3
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@respx.mock
async def test_get_rate_history_carries_forward_across_a_weekend() -> None:
    # 2026-01-09 is a Friday; 10th/11th are Sat/Sun (no published rate);
    # 12th is the following Monday.
    friday, saturday, sunday, monday = (date(2026, 1, 9), date(2026, 1, 10), date(2026, 1, 11), date(2026, 1, 12))
    session = MagicMock()
    session.execute = AsyncMock(return_value=_history_rows_result([]))
    session.add = MagicMock()
    session.commit = AsyncMock()

    respx.get(
        f"{_FRANKFURTER_BASE_URL}/{friday.isoformat()}..{monday.isoformat()}",
        params={"base": "CAD", "symbols": "USD"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={"base": "CAD", "rates": {"2026-01-09": {"USD": 0.72}, "2026-01-12": {"USD": 0.71}}},
        )
    )

    series = await get_rate_history(session, "USD", friday, monday)

    assert series[saturday] == pytest.approx(1 / 0.72)  # carried from Friday
    assert series[sunday] == pytest.approx(1 / 0.72)  # same anchor as Saturday, not re-derived
    assert series[monday] == pytest.approx(1 / 0.71)  # real Monday rate, not carried
    # The weekend gap is never written back — only the two real,
    # Frankfurter-returned dates get persisted.
    assert session.add.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_rate_history_omits_dates_when_the_range_fetch_fails() -> None:
    d1, d2 = date(2026, 1, 5), date(2026, 1, 6)
    session = MagicMock()
    session.execute = AsyncMock(return_value=_history_rows_result([]))
    session.add = MagicMock()
    session.commit = AsyncMock()

    respx.get(f"{_FRANKFURTER_BASE_URL}/{d1.isoformat()}..{d2.isoformat()}").mock(return_value=httpx.Response(500))

    # Mutation-check: removing _fetch_rate_range's try/except would let
    # raise_for_status()'s exception propagate instead of returning {} —
    # this test would error instead of passing.
    series = await get_rate_history(session, "USD", d1, d2)

    assert series == {}
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@respx.mock
async def test_get_rate_history_does_not_carry_forward_across_a_failed_fetch() -> None:
    # A real earlier rate exists, but the requested range's fetch fails
    # outright — must NOT reuse the earlier rate as if the failed dates
    # were just a holiday. That would look identical on a chart to a
    # genuinely-known rate, which is exactly the "never a wrong rate"
    # distinction _fetch_rate_range's None-vs-{} return exists for.
    earlier = date(2026, 1, 2)
    d1, d2 = date(2026, 1, 5), date(2026, 1, 6)
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=_history_rows_result([FxRateHistory(currency="USD", date=earlier, rate_to_cad=1.40)])
    )
    session.add = MagicMock()
    session.commit = AsyncMock()

    respx.get(f"{_FRANKFURTER_BASE_URL}/{d1.isoformat()}..{d2.isoformat()}").mock(return_value=httpx.Response(500))

    series = await get_rate_history(session, "USD", d1, d2)

    assert series == {}  # not {d1: 1.40, d2: 1.40} — carry-forward would be wrong here


@pytest.mark.asyncio
@respx.mock
async def test_get_rate_history_does_not_readd_already_cached_dates_inside_a_refetched_span() -> None:
    # Regression: a non-contiguous `missing` set's min..max re-covers
    # already-known dates sitting in between (e.g. day 1 and day 5
    # missing, days 2-4 already cached) — re-adding one of those would
    # violate the (currency, date) unique constraint on a real DB.
    d1, d2, d3, d4, d5 = (date(2026, 1, i) for i in range(5, 10))
    already_cached = [FxRateHistory(currency="USD", date=d, rate_to_cad=0.70) for d in (d2, d3, d4)]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_history_rows_result(already_cached))
    session.add = MagicMock()
    session.commit = AsyncMock()

    respx.get(
        f"{_FRANKFURTER_BASE_URL}/{d1.isoformat()}..{d5.isoformat()}", params={"base": "CAD", "symbols": "USD"}
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "base": "CAD",
                "rates": {
                    "2026-01-05": {"USD": 0.72},
                    "2026-01-06": {"USD": 0.71},  # already cached, re-returned anyway
                    "2026-01-07": {"USD": 0.705},  # already cached
                    "2026-01-08": {"USD": 0.70},  # already cached
                    "2026-01-09": {"USD": 0.69},
                },
            },
        )
    )

    series = await get_rate_history(session, "USD", d1, d5)

    assert series[d1] == pytest.approx(1 / 0.72)
    assert series[d5] == pytest.approx(1 / 0.69)
    # Only the two genuinely new dates get added — the three already-cached
    # ones must not be re-added even though Frankfurter's range response
    # included them again.
    added_dates = {call.args[0].date for call in session.add.call_args_list}
    assert added_dates == {d1, d5}
