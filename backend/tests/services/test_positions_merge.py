import pytest

from app.services.portfolio import MergedHolding, merge_holdings
from app.services.positions import Holding


def _holding(account: str, symbol: str, shares: float, currency: str, avg_cost: float) -> Holding:
    # avg_cost_cad is not used by the merge, so any value will do
    return Holding(account, symbol, shares, currency, avg_cost, avg_cost)


def test_same_symbol_in_two_accounts_merges_with_weighted_cost() -> None:
    merged = merge_holdings(
        [
            _holding("TFSA", "NVDA", 10, "USD", 100.0),
            _holding("RRSP", "NVDA", 5, "USD", 130.0),
        ]
    )

    assert merged == (MergedHolding("NVDA", "USD", 15, pytest.approx(110.0)),)


def test_usd_stock_and_cad_cdr_with_the_same_symbol_stay_separate() -> None:
    merged = merge_holdings(
        [
            _holding("TFSA", "AVGO", 8, "USD", 250.0),
            _holding("RRSP", "AVGO", 40, "CAD", 12.5),
        ]
    )

    assert merged == (
        MergedHolding("AVGO", "CAD", 40, 12.5),
        MergedHolding("AVGO", "USD", 8, 250.0),
    )


def test_single_account_holding_is_unchanged() -> None:
    merged = merge_holdings([_holding("TFSA", "SOFI", 20, "USD", 8.25)])

    assert merged == (MergedHolding("SOFI", "USD", 20, 8.25),)


def test_different_symbols_stay_separate_and_come_out_sorted() -> None:
    merged = merge_holdings(
        [
            _holding("TFSA", "NVDA", 10, "USD", 100.0),
            _holding("TFSA", "ETN", 3, "USD", 300.0),
            _holding("RRSP", "RY.TO", 7, "CAD", 150.0),
        ]
    )

    assert [m.symbol for m in merged] == ["ETN", "NVDA", "RY.TO"]


def test_zero_cost_bonus_shares_lower_the_average() -> None:
    merged = merge_holdings(
        [
            _holding("TFSA", "XYZ", 5, "USD", 0.0),
            _holding("RRSP", "XYZ", 5, "USD", 10.0),
        ]
    )

    assert merged == (MergedHolding("XYZ", "USD", 10, pytest.approx(5.0)),)


def test_accepts_any_iterable_and_empty_input_gives_an_empty_tuple() -> None:
    assert merge_holdings([]) == ()
    assert merge_holdings(iter([])) == ()
