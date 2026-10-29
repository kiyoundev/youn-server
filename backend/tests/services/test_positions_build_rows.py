from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.services.portfolio import MergedHolding, build_rows
from app.services.prices import PriceQuote

_AT = datetime(2026, 10, 22, 14, 0, tzinfo=timezone.utc)
_TRADED = datetime(2026, 7, 27, 14, 36, tzinfo=timezone.utc)


def _ok(price: float, currency: str | None = None) -> PriceQuote:
    return PriceQuote(price, currency, _AT, "ok")


def test_ok_quote_gives_value_gain_and_pct() -> None:
    (row,) = build_rows([MergedHolding("NVDA", "USD", 15, 110.0, _TRADED)], {("NVDA", "USD"): _ok(120.0)}, {})

    assert row.invested == pytest.approx(1650.0)
    assert row.current_price == 120.0
    assert row.market_value == pytest.approx(1800.0)
    assert row.unrealized_gain == pytest.approx(150.0)
    assert row.unrealized_gain_pct == pytest.approx(150 / 1650)
    assert (row.price_status, row.price_as_of) == ("ok", _AT)


def test_loss_gives_negative_gain_and_pct() -> None:
    (row,) = build_rows([MergedHolding("NVDA", "USD", 10, 100.0, _TRADED)], {("NVDA", "USD"): _ok(80.0)}, {})

    assert row.unrealized_gain == pytest.approx(-200.0)
    assert row.unrealized_gain_pct == pytest.approx(-0.2)


def test_stale_quote_is_still_valued_and_keeps_its_age() -> None:
    old = PriceQuote(13.08, "CAD", _AT, "stale")
    (row,) = build_rows([MergedHolding("AVGO", "CAD", 40, 12.5, _TRADED)], {("AVGO", "CAD"): old}, {})

    assert row.market_value == pytest.approx(523.2)
    assert (row.price_status, row.price_as_of) == ("stale", _AT)


def test_unavailable_keeps_invested_and_blanks_the_rest() -> None:
    quote = PriceQuote(None, None, None, "unavailable")
    (row,) = build_rows([MergedHolding("SOFI", "USD", 20, 8.25, _TRADED)], {("SOFI", "USD"): quote}, {})

    assert row.invested == pytest.approx(165.0)
    assert (row.current_price, row.market_value, row.unrealized_gain, row.unrealized_gain_pct) == (
        None, None, None, None,
    )
    assert row.price_status == "unavailable"


def test_currency_mismatch_withholds_the_price() -> None:
    quote = PriceQuote(None, "USD", _AT, "currency_mismatch")
    (row,) = build_rows([MergedHolding("AVGO", "CAD", 40, 12.5, _TRADED)], {("AVGO", "CAD"): quote}, {})

    assert (row.current_price, row.market_value) == (None, None)
    assert (row.price_status, row.price_as_of) == ("currency_mismatch", _AT)


def test_zero_cost_holding_has_gain_but_no_pct() -> None:
    (row,) = build_rows([MergedHolding("XYZ", "USD", 5, 0.0, _TRADED)], {("XYZ", "USD"): _ok(10.0)}, {})

    assert row.invested == 0
    assert row.unrealized_gain == pytest.approx(50.0)
    assert row.unrealized_gain_pct is None


def test_missing_quote_is_treated_as_unavailable() -> None:
    (row,) = build_rows([MergedHolding("NVDA", "USD", 1, 100.0, _TRADED)], {}, {})

    assert (row.price_status, row.market_value) == ("unavailable", None)


def test_sorted_by_value_desc_with_unpriced_last_and_ties_by_symbol() -> None:
    holdings = [
        MergedHolding("AAA", "USD", 1, 1.0, _TRADED),
        MergedHolding("BBB", "USD", 1, 1.0, _TRADED),
        MergedHolding("CCC", "USD", 1, 1.0, _TRADED),
        MergedHolding("DDD", "USD", 1, 1.0, _TRADED),
        MergedHolding("EEE", "USD", 1, 1.0, _TRADED),
    ]
    quotes = {
        ("AAA", "USD"): _ok(50.0),
        ("BBB", "USD"): _ok(200.0),
        ("CCC", "USD"): PriceQuote(None, None, None, "unavailable"),
        ("DDD", "USD"): _ok(50.0),
        # EEE has no quote at all
    }

    assert [r.symbol for r in build_rows(holdings, quotes, {})] == ["BBB", "AAA", "DDD", "CCC", "EEE"]


def test_last_traded_reaches_the_row_even_when_unpriced() -> None:
    priced, unpriced = build_rows(
        [MergedHolding("NVDA", "USD", 1, 100.0, _TRADED), MergedHolding("SOFI", "USD", 1, 1.0, _AT)],
        {("NVDA", "USD"): _ok(120.0)},
        {},
    )

    assert (priced.last_traded_at, unpriced.last_traded_at) == (_TRADED, _AT)


def test_asset_type_is_looked_up_by_symbol_and_currency() -> None:
    # the USD stock AVGO and the CAD CDR AVGO are different rows with different types
    cdr, stock = build_rows(  # unpriced rows tie-break by currency, CAD first
        [MergedHolding("AVGO", "USD", 1, 100.0, _TRADED), MergedHolding("AVGO", "CAD", 1, 10.0, _TRADED)],
        {},
        {("AVGO", "USD"): "Stock", ("AVGO", "CAD"): "CDR"},
    )

    assert (stock.native_currency, stock.asset_type) == ("USD", "Stock")
    assert (cdr.native_currency, cdr.asset_type) == ("CAD", "CDR")


def test_unknown_type_is_none_whether_missing_or_failed() -> None:
    missing, failed = build_rows(
        [MergedHolding("AAA", "USD", 1, 1.0, _TRADED), MergedHolding("BBB", "USD", 1, 1.0, _TRADED)],
        {},
        {("BBB", "USD"): None},
    )

    assert (missing.asset_type, failed.asset_type) == (None, None)


def test_asset_type_never_changes_a_price_field() -> None:
    holdings = [MergedHolding("NVDA", "USD", 15, 110.0, _TRADED)]
    quotes = {("NVDA", "USD"): _ok(120.0)}

    (without,) = build_rows(holdings, quotes, {})
    (with_type,) = build_rows(holdings, quotes, {("NVDA", "USD"): "Stock"})

    assert replace(with_type, asset_type=None) == without


def test_empty_input_gives_empty_tuple() -> None:
    assert build_rows([], {}, {}) == ()
