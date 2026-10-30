from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.ledger_errors import LedgerImportError
from app.services.positions import compute_positions
from app.services.wealthsimple_csv import ParsedRow, _parse_row, _read_rows

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wealthsimple"


def _parsed(name: str) -> list[ParsedRow]:
    """Parses a fixture straight to rows, bypassing _check_allowlist — lets
    with_sell.csv's placeholder sell through, since compute_positions
    itself doesn't care about the allowlist (that's parse_export's job)."""
    text = (FIXTURES / name).read_text()
    raw_rows = _read_rows(text)
    rows = [_parse_row(r, i + 2) for i, r in enumerate(raw_rows)]
    return sorted(rows, key=lambda r: r.effective_at)


def _row(day: int, month: int = 1, year: int = 2026, hour: int = 9, **overrides) -> ParsedRow:
    base = dict(
        effective_at=datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc),
        settlement_date=None,
        account_id="A",
        account_type="TFSA",
        activity_type="MoneyMovement",
        activity_sub_type="EFT",
        description="deposit",
        direction=None,
        symbol=None,
        name=None,
        currency="CAD",
        quantity=None,
        unit_price=None,
        fx_rate=None,
        commission=0.0,
        net_cash_amount=0.0,
    )
    base.update(overrides)
    return ParsedRow(**base)


def _deposit(day: int, amount: float = 10_000.0) -> ParsedRow:
    return _row(day, net_cash_amount=amount)


def _buy(day: int, symbol: str, quantity: float, unit_price: float, fx_rate: float | None = None) -> ParsedRow:
    cash = -(quantity * unit_price)
    return _row(
        day, activity_type="Trade", activity_sub_type="BUY", direction="LONG", symbol=symbol,
        quantity=quantity, unit_price=unit_price, fx_rate=fx_rate, net_cash_amount=cash,
    )


def _sell(day: int, symbol: str, quantity: float, unit_price: float, fx_rate: float | None = None) -> ParsedRow:
    cash = quantity * unit_price
    return _row(
        day, activity_type="Trade", activity_sub_type="SELL", direction="SHORT", symbol=symbol,
        quantity=quantity, unit_price=unit_price, fx_rate=fx_rate, net_cash_amount=cash,
    )


def test_empty_activities_returns_empty():
    assert compute_positions([]) == ([], 0.0, [])


def test_base_fixture_matches_documented_values():
    holdings, cash, warnings = compute_positions(_parsed("base.csv"))
    assert cash == pytest.approx(869.14, abs=0.01)
    assert warnings == []

    by_symbol = {h.symbol: h for h in holdings}
    aapl = by_symbol["AAPL"]
    assert aapl.shares == pytest.approx(15.0)
    assert aapl.native_currency == "USD"
    assert aapl.avg_cost_native == pytest.approx(207.93, abs=0.01)
    assert aapl.avg_cost_cad == pytest.approx(302.20, abs=0.01)

    xeqt = by_symbol["XEQT.TO"]
    assert xeqt.shares == pytest.approx(20.0)
    assert xeqt.native_currency == "CAD"
    assert xeqt.avg_cost_native == pytest.approx(30.0, abs=0.01)
    assert xeqt.avg_cost_cad == pytest.approx(30.0, abs=0.01)


def test_sell_reduces_shares_but_avg_cost_is_unchanged():
    base_holdings, _, _ = compute_positions(_parsed("base.csv"))
    sell_holdings, cash, _ = compute_positions(_parsed("with_sell.csv"))

    base_aapl = {h.symbol: h for h in base_holdings}["AAPL"]
    sell_aapl = {h.symbol: h for h in sell_holdings}["AAPL"]

    assert sell_aapl.shares == base_aapl.shares - 5
    assert sell_aapl.avg_cost_native == pytest.approx(base_aapl.avg_cost_native)
    assert sell_aapl.avg_cost_cad == pytest.approx(base_aapl.avg_cost_cad)
    assert cash == pytest.approx(2444.14, abs=0.01)


def test_fx_conversion_spec_example_300_cad_at_1_45_is_206_90_usd():
    # The spec's own canonical example (decision 3, .doc/issues.md).
    rows = [_deposit(1), _buy(2, "X", quantity=1.0, unit_price=300.00, fx_rate=1.4500)]
    holdings, _, _ = compute_positions(rows)
    assert holdings[0].avg_cost_native == pytest.approx(206.90, abs=0.01)


def test_oversell_raises_negative_holdings():
    rows = [_deposit(1), _buy(2, "X", 5.0, 10.0), _sell(3, "X", 10.0, 10.0)]
    with pytest.raises(LedgerImportError) as exc:
        compute_positions(rows)
    assert exc.value.code == "negative_holdings"


def test_buy_without_funding_raises_negative_cash():
    rows = [_buy(1, "X", 1.0, 100.0)]
    with pytest.raises(LedgerImportError) as exc:
        compute_positions(rows)
    assert exc.value.code == "negative_cash"


def test_mixed_fx_presence_on_one_symbol_raises():
    rows = [_deposit(1), _buy(2, "MIX", 1.0, 100.0, fx_rate=1.45), _buy(3, "MIX", 1.0, 100.0, fx_rate=None)]
    with pytest.raises(LedgerImportError) as exc:
        compute_positions(rows)
    assert exc.value.code == "mixed_native_currency"


def test_fully_sold_position_is_excluded_not_returned_as_zero():
    rows = [_deposit(1), _buy(2, "X", 10.0, 10.0), _sell(3, "X", 10.0, 10.0)]
    holdings, _, _ = compute_positions(rows)
    assert holdings == []


def test_rebuy_after_full_sell_starts_a_clean_cost_basis():
    rows = [
        _deposit(1),
        _buy(2, "X", 10.0, 100.0),   # cost basis 100/share
        _sell(3, "X", 10.0, 999.0),  # fully sold — resets, regardless of sell price
        _buy(4, "X", 5.0, 50.0),     # new cost basis should be 50, not blended with the old 100
    ]
    holdings, _, _ = compute_positions(rows)
    assert holdings[0].avg_cost_cad == pytest.approx(50.0)


def test_last_traded_at_is_the_latest_trade_whatever_the_input_order():
    rows = [_deposit(1), _buy(2, "X", 1.0, 10.0), _buy(9, "X", 1.0, 10.0), _buy(5, "X", 1.0, 10.0)]
    (holding,) = compute_positions(rows[::-1])[0]
    assert holding.last_traded_at == datetime(2026, 1, 9, 9, 0, 0, tzinfo=timezone.utc)


def test_a_partial_sell_counts_as_the_last_trade():
    rows = [_deposit(1), _buy(2, "X", 10.0, 10.0), _sell(5, "X", 4.0, 10.0)]
    (holding,) = compute_positions(rows)[0]
    assert holding.shares == pytest.approx(6.0)
    assert holding.last_traded_at == datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc)


def test_last_traded_at_after_a_rebuy_is_the_rebuy_not_the_old_trade():
    rows = [_deposit(1), _buy(2, "X", 10.0, 10.0), _sell(3, "X", 10.0, 10.0), _buy(7, "X", 5.0, 10.0)]
    (holding,) = compute_positions(rows)[0]
    assert holding.last_traded_at == datetime(2026, 1, 7, 9, 0, 0, tzinfo=timezone.utc)


def test_a_dividend_does_not_move_last_traded_at():
    dividend = _row(20, activity_type="Dividend", activity_sub_type="-", symbol="X", net_cash_amount=6.14)
    (holding,) = compute_positions([_deposit(1), _buy(2, "X", 1.0, 10.0), dividend])[0]
    assert holding.last_traded_at == datetime(2026, 1, 2, 9, 0, 0, tzinfo=timezone.utc)


def test_each_account_keeps_its_own_last_traded_at():
    rows = [_deposit(1), _buy(2, "X", 1.0, 10.0), replace(_buy(8, "X", 1.0, 10.0), account_id="B")]
    by_account = {h.account_id: h.last_traded_at.day for h in compute_positions(rows)[0]}
    assert by_account == {"A": 2, "B": 8}


def test_warning_when_first_row_is_not_a_funding_deposit():
    # A dividend as the very first row: positive cash, so no negative_cash
    # error, but it's not a MoneyMovement deposit either.
    rows = [_row(1, activity_type="Dividend", activity_sub_type="-", symbol="X", net_cash_amount=5.0)]
    _, _, warnings = compute_positions(rows)
    assert len(warnings) == 1
    assert "funding deposit" in warnings[0]


def test_no_warning_when_first_row_is_a_deposit():
    holdings, cash, warnings = compute_positions(_parsed("base.csv"))
    assert warnings == []


def test_zero_cost_buy_is_a_buy_not_a_sell():
    # A bonus share: cash out is 0. `net_cash_amount < 0` used to send this
    # down the sell branch, rejecting the whole import as negative_holdings.
    rows = [
        _deposit(1),
        _buy(2, "X", 10.0, 10.0),  # 10 shares for 100
        _row(3, activity_type="Trade", activity_sub_type="BUY", direction="LONG", symbol="X",
             quantity=10.0, unit_price=0.0, net_cash_amount=0.0),  # 10 more for free
    ]
    holdings, cash, _ = compute_positions(rows)
    assert holdings[0].shares == pytest.approx(20.0)
    assert holdings[0].avg_cost_cad == pytest.approx(5.0)  # 100 / 20 — the free shares pull it down
    assert cash == pytest.approx(10_000.0 - 100.0)


@pytest.mark.parametrize("field", ["symbol", "quantity", "unit_price"])
def test_trade_row_missing_a_required_field_is_a_malformed_row_not_an_assertion(field):
    # The parser guarantees these; this is the backstop for a row that got in
    # some other way (and unlike an assert it survives `python -O`).
    trade = _buy(2, "X", 1.0, 10.0)
    object.__setattr__(trade, field, None)  # ParsedRow is frozen
    with pytest.raises(LedgerImportError) as exc:
        compute_positions([_deposit(1), trade])
    assert exc.value.code == "malformed_row"
    assert exc.value.details["missing"] == [field]


def test_zero_quantity_sell_of_an_unheld_symbol_does_not_divide_by_zero():
    # A sell passes the oversell check (0 > 0 is false) with nothing held, then
    # reaches the average-cost step — which must not divide by zero shares.
    # Positive proceeds with quantity 0 — built by hand, because the _sell helper
    # computes proceeds as quantity * price = 0, which is classified as a buy.
    sell = _row(2, activity_type="Trade", activity_sub_type="SELL", direction="SHORT", symbol="X",
                quantity=0.0, unit_price=10.0, net_cash_amount=1.0)
    holdings, cash, _ = compute_positions([_deposit(1), sell])
    assert holdings == []
    assert cash == pytest.approx(10_001.0)
