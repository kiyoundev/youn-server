from dataclasses import asdict, fields
from datetime import datetime, timezone

import pytest

from app.schemas.positions import CurrencySubtotal, PortfolioSummary
from app.services.portfolio import CurrencyTotals, PositionRow, SummaryData, build_summary

_TRADED = datetime(2026, 7, 27, 14, 36, tzinfo=timezone.utc)


def _row(symbol, currency, shares, avg_cost, price, status="ok") -> PositionRow:
    invested = shares * avg_cost
    value = None if price is None else shares * price
    gain = None if value is None else value - invested
    pct = None if gain is None or not invested else gain / invested
    return PositionRow(symbol, currency, shares, avg_cost, invested, price, status, None, value, gain, pct, _TRADED, None)


# 15 NVDA @110 priced 120 (+150) | 20 SOFI @8.25 unpriced | 40 AVGO CDR @12.5 priced 13.08 (stale)
NVDA = _row("NVDA", "USD", 15, 110.0, 120.0)
SOFI = _row("SOFI", "USD", 20, 8.25, None, "unavailable")
AVGO = _row("AVGO", "CAD", 40, 12.5, 13.08, "stale")


def test_subtotals_cover_each_currency_usd_first() -> None:
    summary = build_summary([AVGO, SOFI, NVDA], cash=200.0, usd_rate=1.38, usd_rate_stale=False)

    usd, cad = summary.subtotals
    assert (usd.currency, usd.holdings_count, usd.unpriced_count) == ("USD", 2, 1)
    assert usd.invested == pytest.approx(1815.0)  # every holding, priced or not
    assert usd.market_value == pytest.approx(1800.0)
    assert usd.unrealized_gain == pytest.approx(150.0)
    assert (cad.currency, cad.holdings_count, cad.unpriced_count) == ("CAD", 1, 0)
    assert cad.market_value == pytest.approx(523.2)  # a stale price still counts


def test_pct_is_against_the_priced_holdings_cost_only() -> None:
    summary = build_summary([NVDA, SOFI], cash=0.0, usd_rate=1.38, usd_rate_stale=False)

    # 150 / 1650 (NVDA alone), not 150 / 1815: the unpriced SOFI must not dilute it
    assert summary.subtotals[0].unrealized_gain_pct == pytest.approx(150 / 1650)


def test_balance_converts_usd_at_todays_rate() -> None:
    summary = build_summary([NVDA, SOFI, AVGO], cash=200.0, usd_rate=1.38, usd_rate_stale=False)

    assert summary.balance_cad == pytest.approx(523.2 + 1800.0 * 1.38 + 200.0)
    assert (summary.fx_available, summary.fx_stale) == (True, False)
    assert (summary.cash_cad, summary.unpriced_count) == (200.0, 1)


def test_stale_rate_is_still_used_and_flagged() -> None:
    summary = build_summary([NVDA], cash=0.0, usd_rate=1.40, usd_rate_stale=True)

    assert summary.balance_cad == pytest.approx(1800.0 * 1.40)
    assert (summary.fx_available, summary.fx_stale) == (True, True)


def test_usd_holdings_with_no_rate_give_no_balance() -> None:
    summary = build_summary([NVDA, AVGO], cash=200.0, usd_rate=None, usd_rate_stale=False)

    assert summary.balance_cad is None
    assert (summary.fx_available, summary.fx_stale) == (False, False)
    assert summary.subtotals[0].market_value == pytest.approx(1800.0)  # per-currency totals survive


def test_no_usd_holdings_needs_no_rate() -> None:
    # a missing or stale rate must not flag a balance that never used it
    summary = build_summary([AVGO], cash=200.0, usd_rate=None, usd_rate_stale=True)

    assert summary.balance_cad == pytest.approx(523.2 + 200.0)
    assert (summary.fx_available, summary.fx_stale) == (True, False)


def test_usd_holdings_all_unpriced_need_no_rate() -> None:
    summary = build_summary([SOFI, AVGO], cash=0.0, usd_rate=None, usd_rate_stale=True)

    assert summary.balance_cad == pytest.approx(523.2)
    assert (summary.fx_available, summary.fx_stale) == (True, False)
    assert summary.unpriced_count == 1


def test_all_unpriced_currency_has_zero_value_and_no_pct() -> None:
    (usd,) = build_summary([SOFI], cash=0.0, usd_rate=1.38, usd_rate_stale=False).subtotals

    assert (usd.market_value, usd.unrealized_gain, usd.unrealized_gain_pct) == (0.0, 0.0, None)
    assert usd.invested == pytest.approx(165.0)


def test_empty_ledger_balance_is_just_cash() -> None:
    summary = build_summary([], cash=0.0, usd_rate=None, usd_rate_stale=False)

    assert summary == SummaryData((), 0.0, 0.0, True, False, 0)


def test_dataclasses_have_exactly_the_fields_of_their_schemas() -> None:
    # the route maps with PortfolioSummary(**asdict(summary)); drift would only fail at request time
    assert {f.name for f in fields(SummaryData)} == set(PortfolioSummary.model_fields)
    assert {f.name for f in fields(CurrencyTotals)} == set(CurrencySubtotal.model_fields)


def test_summary_maps_to_the_schema_through_asdict() -> None:
    summary = build_summary([NVDA, AVGO], cash=200.0, usd_rate=1.38, usd_rate_stale=False)

    out = PortfolioSummary(**asdict(summary))

    assert [s.currency for s in out.subtotals] == ["USD", "CAD"]
    assert out.balance_cad == pytest.approx(summary.balance_cad)
