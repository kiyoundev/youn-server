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


def _alloc(holdings, quotes, rate):
    return {r.symbol: r.allocation for r in build_rows(holdings, quotes, {}, rate)}


def test_allocation_is_each_rows_share_of_the_total_in_cad() -> None:
    holdings = [MergedHolding("NVDA", "USD", 10, 90.0, _TRADED), MergedHolding("XYZ", "CAD", 10, 50.0, _TRADED)]
    quotes = {("NVDA", "USD"): _ok(100.0), ("XYZ", "CAD"): _ok(60.0)}

    alloc = _alloc(holdings, quotes, 1.4)  # 1000 USD = 1400 CAD, and 600 CAD

    assert alloc == {"NVDA": pytest.approx(0.7), "XYZ": pytest.approx(0.3)}


def test_allocations_add_up_to_one() -> None:
    holdings = [MergedHolding(s, c, 3, 1.0, _TRADED) for s, c in (("A", "USD"), ("B", "CAD"), ("C", "USD"))]
    quotes = {("A", "USD"): _ok(7.0), ("B", "CAD"): _ok(11.0), ("C", "USD"): _ok(13.0)}

    assert sum(_alloc(holdings, quotes, 1.37).values()) == pytest.approx(1.0)


def test_an_unpriced_row_has_no_allocation_and_is_left_out_of_the_total() -> None:
    holdings = [MergedHolding("AAA", "CAD", 1, 1.0, _TRADED), MergedHolding("BBB", "CAD", 1, 1.0, _TRADED)]
    quotes = {("AAA", "CAD"): _ok(50.0), ("BBB", "CAD"): PriceQuote(None, None, None, "unavailable")}

    assert _alloc(holdings, quotes, None) == {"AAA": pytest.approx(1.0), "BBB": None}


def test_a_stale_price_still_counts_toward_allocation() -> None:
    holdings = [MergedHolding("AAA", "CAD", 1, 1.0, _TRADED), MergedHolding("BBB", "CAD", 1, 1.0, _TRADED)]
    quotes = {("AAA", "CAD"): _ok(75.0), ("BBB", "CAD"): PriceQuote(25.0, "CAD", _AT, "stale")}

    assert _alloc(holdings, quotes, None) == {"AAA": pytest.approx(0.75), "BBB": pytest.approx(0.25)}


def test_without_a_usd_rate_every_row_is_none_even_the_cad_ones() -> None:
    holdings = [MergedHolding("NVDA", "USD", 1, 1.0, _TRADED), MergedHolding("XYZ", "CAD", 1, 1.0, _TRADED)]
    quotes = {("NVDA", "USD"): _ok(100.0), ("XYZ", "CAD"): _ok(60.0)}

    assert _alloc(holdings, quotes, None) == {"NVDA": None, "XYZ": None}


def test_cad_only_holdings_need_no_rate() -> None:
    holdings = [MergedHolding("XYZ", "CAD", 1, 1.0, _TRADED)]

    assert _alloc(holdings, {("XYZ", "CAD"): _ok(60.0)}, None) == {"XYZ": pytest.approx(1.0)}


def test_a_usd_row_with_no_price_does_not_need_the_rate() -> None:
    holdings = [MergedHolding("NVDA", "USD", 1, 1.0, _TRADED), MergedHolding("XYZ", "CAD", 1, 1.0, _TRADED)]
    quotes = {("NVDA", "USD"): PriceQuote(None, None, None, "unavailable"), ("XYZ", "CAD"): _ok(60.0)}

    assert _alloc(holdings, quotes, None) == {"NVDA": None, "XYZ": pytest.approx(1.0)}


def test_nothing_priced_or_a_zero_total_gives_no_allocation() -> None:
    holdings = [MergedHolding("XYZ", "CAD", 1, 1.0, _TRADED)]

    assert _alloc(holdings, {}, 1.4) == {"XYZ": None}
    assert _alloc(holdings, {("XYZ", "CAD"): _ok(0.0)}, 1.4) == {"XYZ": None}


def test_rows_are_ordered_by_cad_value_when_a_rate_is_known() -> None:
    # 1500 CAD beats 1200 USD in native units, but 1200 USD is 1680 CAD
    holdings = [MergedHolding("CADCO", "CAD", 10, 1.0, _TRADED), MergedHolding("USCO", "USD", 10, 1.0, _TRADED)]
    quotes = {("CADCO", "CAD"): _ok(150.0), ("USCO", "USD"): _ok(120.0)}

    assert [r.symbol for r in build_rows(holdings, quotes, {}, 1.4)] == ["USCO", "CADCO"]
    assert [r.symbol for r in build_rows(holdings, quotes, {}, None)] == ["CADCO", "USCO"]  # no rate: native values


def test_empty_input_gives_empty_tuple() -> None:
    assert build_rows([], {}, {}) == ()
