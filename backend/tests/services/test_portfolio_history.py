"""Tests for app.services.portfolio_history.get_portfolio_history (issue #23)."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import portfolio_history
from app.services.wealthsimple_csv import LEDGER_TZ

# LEDGER_TZ (Toronto), not UTC: get_portfolio_history's own `today` is
# datetime.now(LEDGER_TZ).date(), which disagrees with a UTC "today" for
# ~5h/day (UTC midnight to ~5am, while Toronto is still "yesterday") — a
# fixture that used UTC here flaked in exactly that window.
_NOW = datetime.now(LEDGER_TZ).replace(hour=12, minute=0, second=0, microsecond=0)


def _days_ago(n: int) -> datetime:
    return _NOW - timedelta(days=n)


def _activity(days_ago: int, activity_type: str, **kw) -> SimpleNamespace:
    base = dict(
        account_id="TFSA",
        effective_at=_days_ago(days_ago),
        activity_type=activity_type,
        symbol=None,
        quantity=None,
        unit_price=None,
        net_cash_amount=0.0,
        fx_rate=None,
    )
    return SimpleNamespace(**{**base, **kw})


class _FakeDb:
    def __init__(self, rows: list) -> None:
        self.rows = rows

    async def execute(self, _stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.rows))


class _FakeFinnhub:
    """Hands back a canned {ticker: [{date, close}, ...]} series per call."""

    def __init__(self, series: dict[str, list[dict]]) -> None:
        self.series = series
        self.calls: list[tuple] = []

    async def get_price_history(self, ticker, range_, native_currency):
        self.calls.append((ticker, range_, native_currency))
        return self.series.get(ticker, [])


async def _fake_rate_history(_db, _currency, start, end):
    return {start + timedelta(days=i): 1.35 for i in range((end - start).days + 1)}


@pytest.fixture(autouse=True)
def _fx(monkeypatch):
    monkeypatch.setattr(portfolio_history, "get_rate_history", _fake_rate_history)


@pytest.mark.asyncio
async def test_empty_ledger_is_an_empty_list() -> None:
    result = await portfolio_history.get_portfolio_history(_FakeDb([]), "1M", _FakeFinnhub({}))
    assert result == []


@pytest.mark.asyncio
async def test_all_range_anchors_to_the_earliest_activity_not_a_fixed_window() -> None:
    activities = [_activity(50, "MoneyMovement", net_cash_amount=5_000.0)]

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "ALL", _FakeFinnhub({}))

    assert result[0]["date"] == _days_ago(50).date().isoformat()
    assert len(result) == 51  # 50 days ago through today, inclusive
    assert all(p["value"] == 5_000.0 for p in result)  # all-cash ledger: flat line


@pytest.mark.asyncio
@pytest.mark.parametrize("range_,expected_points", [("1W", 8), ("1M", 31), ("3M", 91), ("6M", 181)])
async def test_each_fixed_range_produces_one_point_per_calendar_day(range_: str, expected_points: int) -> None:
    activities = [_activity(200, "MoneyMovement", net_cash_amount=1_000.0)]  # older than every window below

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), range_, _FakeFinnhub({}))

    assert len(result) == expected_points


@pytest.mark.asyncio
async def test_1w_parses_its_hourly_bars_and_collapses_them_to_one_point_per_day() -> None:
    # 1W resolves to yfinance interval "1h" (is_intraday_range is True for
    # it, same as 1D) — get_price_history writes full timestamps for it, not
    # plain dates. Regression for the bug where portfolio_history tried to
    # date.fromisoformat() those timestamps because its own is_1d flag
    # (range_ == "1D") doesn't cover 1W — this parses them correctly, and
    # also collapses the day's several hourly bars down to one chart point.
    activities = [
        _activity(6, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(6, "Trade", symbol="AAPL", quantity=10.0, unit_price=100.0, net_cash_amount=-1000.0),
    ]
    day1, day0 = _days_ago(1).date().isoformat(), _days_ago(0).date().isoformat()
    prices = {
        "AAPL": [
            {"date": f"{day1} 09:30:00-04:00", "close": 100.0},
            {"date": f"{day1} 15:30:00-04:00", "close": 105.0},  # day1's latest bar should win
            {"date": f"{day0} 09:30:00-04:00", "close": 108.0},
            {"date": f"{day0} 15:30:00-04:00", "close": 110.0},  # day0's latest bar should win
        ]
    }

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1W", _FakeFinnhub(prices))

    by_date = {p["date"]: p["value"] for p in result}
    assert by_date[day1] == 9_000.0 + 10 * 105.0  # not 100.0 — the day's last bar, not its first
    assert by_date[day0] == 9_000.0 + 10 * 110.0
    assert all(" " not in p["date"] for p in result)  # one plain date per point, not one per hourly bar


@pytest.mark.asyncio
async def test_ytd_anchors_to_january_first_of_this_year() -> None:
    activities = [_activity(400, "MoneyMovement", net_cash_amount=1_000.0)]

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "YTD", _FakeFinnhub({}))

    assert result[0]["date"] == date(_NOW.year, 1, 1).isoformat()


@pytest.mark.asyncio
async def test_a_stock_bought_mid_range_contributes_nothing_before_its_first_buy() -> None:
    activities = [
        _activity(20, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(10, "Trade", symbol="AAPL", quantity=10.0, unit_price=100.0, net_cash_amount=-1000.0),
    ]
    prices = {"AAPL": [{"date": _days_ago(d).date().isoformat(), "close": 100.0} for d in range(20, -1, -1)]}

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1M", _FakeFinnhub(prices))

    by_date = {p["date"]: p["value"] for p in result}
    assert by_date[_days_ago(15).date().isoformat()] == 10_000.0  # before the buy: cash only, AAPL excluded
    assert by_date[_days_ago(10).date().isoformat()] == 9_000.0 + 10 * 100.0  # buy day onward: priced in


@pytest.mark.asyncio
async def test_a_missing_close_carries_forward_the_last_known_price() -> None:
    activities = [
        _activity(20, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(15, "Trade", symbol="AAPL", quantity=10.0, unit_price=100.0, net_cash_amount=-1000.0),
    ]
    # no close 5 days ago -> that point must carry forward 6-days-ago's price
    prices = {
        "AAPL": [
            {"date": _days_ago(d).date().isoformat(), "close": 100.0 + (15 - d)}
            for d in range(15, -1, -1)
            if d != 5
        ]
    }

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1M", _FakeFinnhub(prices))

    by_date = {p["date"]: p["value"] for p in result}
    price_6_days_ago = 100.0 + (15 - 6)
    assert by_date[_days_ago(5).date().isoformat()] == 9_000.0 + 10 * price_6_days_ago


@pytest.mark.asyncio
async def test_a_symbol_with_no_price_data_anywhere_is_excluded_and_logged_not_zeroed(caplog) -> None:
    activities = [
        _activity(10, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(5, "Trade", symbol="DELISTED", quantity=10.0, unit_price=50.0, net_cash_amount=-500.0),
    ]

    with caplog.at_level("WARNING"):
        result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1M", _FakeFinnhub({}))

    by_date = {p["date"]: p["value"] for p in result}
    assert by_date[_days_ago(0).date().isoformat()] == 9_500.0  # cash only; a fabricated 0 would give the same
    assert "DELISTED" in caplog.text  # the only observable proof this was excluded, not silently zeroed


@pytest.mark.asyncio
async def test_usd_holdings_are_converted_through_get_rate_history() -> None:
    activities = [
        _activity(10, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(5, "Trade", symbol="AVGO", quantity=2.0, unit_price=200.0, net_cash_amount=-400.0, fx_rate=1.35),
    ]
    prices = {"AVGO": [{"date": _days_ago(d).date().isoformat(), "close": 200.0} for d in range(5, -1, -1)]}

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1M", _FakeFinnhub(prices))

    by_date = {p["date"]: p for p in result}
    today = by_date[_days_ago(0).date().isoformat()]
    assert today["value"] == 9_600.0 + 2 * 200.0 * 1.35
    assert today["total_deposits_cad"] == 10_000.0  # MoneyMovement only; the Trade doesn't count


@pytest.mark.asyncio
async def test_total_deposits_cad_is_cumulative_and_ignores_trades() -> None:
    activities = [
        _activity(20, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(10, "Trade", symbol="AAPL", quantity=10.0, unit_price=100.0, net_cash_amount=-1000.0),
        _activity(5, "MoneyMovement", net_cash_amount=2_000.0),
    ]
    prices = {"AAPL": [{"date": _days_ago(d).date().isoformat(), "close": 100.0} for d in range(20, -1, -1)]}

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1M", _FakeFinnhub(prices))

    by_date = {p["date"]: p for p in result}
    assert by_date[_days_ago(15).date().isoformat()]["total_deposits_cad"] == 10_000.0  # before the 2nd deposit
    assert by_date[_days_ago(5).date().isoformat()]["total_deposits_cad"] == 12_000.0  # after it; Trade untouched
    assert by_date[_days_ago(0).date().isoformat()]["total_deposits_cad"] == 12_000.0  # stays flat afterward


@pytest.mark.asyncio
async def test_total_deposits_cad_is_zero_for_a_ledger_with_only_a_withdrawal_netting_out() -> None:
    activities = [
        _activity(200, "MoneyMovement", net_cash_amount=5_000.0),  # older than the 1M window
        _activity(5, "MoneyMovement", net_cash_amount=-5_000.0),
    ]

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1M", _FakeFinnhub({}))

    today = {p["date"]: p for p in result}[_days_ago(0).date().isoformat()]
    assert today["value"] == 0.0
    assert today["total_deposits_cad"] == 0.0  # net zero: deposit and withdrawal cancel out


@pytest.mark.asyncio
async def test_1d_uses_one_constant_holdings_snapshot_for_every_intraday_point(monkeypatch) -> None:
    activities = [
        _activity(5, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(2, "Trade", symbol="AAPL", quantity=10.0, unit_price=100.0, net_cash_amount=-1000.0),
    ]
    today_iso = _NOW.date().isoformat()
    # -04:00 offset, matching yfinance's real tz-aware intraday index — a
    # naive "no offset" string here would hide a parser regression, exactly
    # how it hid one in production (fromisoformat raised under the backend
    # image's Python 3.10 on this exact shape; _price_series now uses
    # strptime with an explicit %z instead).
    bar_930 = f"{today_iso} 09:30:00-04:00"
    bar_935 = f"{today_iso} 09:35:00-04:00"
    bar_940 = f"{today_iso} 09:40:00-04:00"
    prices = {
        "AAPL": [
            {"date": bar_930, "close": 150.0},
            {"date": bar_935, "close": 151.0},
            {"date": bar_940, "close": 149.0},
        ]
    }

    calls: list[int] = []
    real_compute_positions = portfolio_history.compute_positions

    def _spy(acts):
        calls.append(len(list(acts)))
        return real_compute_positions(acts)

    monkeypatch.setattr(portfolio_history, "compute_positions", _spy)

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1D", _FakeFinnhub(prices))

    assert len(calls) == 1  # one snapshot, reused for every intraday point — not one per point
    assert len(result) == 3  # one per fetched intraday bar
    by_date = {p["date"]: p["value"] for p in result}
    assert by_date[bar_930] == 9_000.0 + 10 * 150.0
    assert by_date[bar_940] == 9_000.0 + 10 * 149.0  # same 10 shares, only price moved


@pytest.mark.asyncio
async def test_1d_backfills_a_symbol_missing_before_its_own_first_bar() -> None:
    # Regression: AAPL's first bar lags MSFT's by 5 minutes (a reporting-lag
    # artifact, not "not bought yet" — both are already held all day for 1D).
    # Before the backfill fix, AAPL was excluded at 09:30, making that point's
    # (and so the frontend's "start of day" baseline's) total understate the
    # real portfolio by AAPL's whole value.
    activities = [
        _activity(5, "MoneyMovement", net_cash_amount=10_000.0),
        _activity(2, "Trade", symbol="AAPL", quantity=10.0, unit_price=100.0, net_cash_amount=-1000.0),
        _activity(2, "Trade", symbol="MSFT", quantity=5.0, unit_price=200.0, net_cash_amount=-1000.0),
    ]
    today_iso = _NOW.date().isoformat()
    prices = {
        "AAPL": [{"date": f"{today_iso} 09:35:00-04:00", "close": 150.0}],  # starts 5 min later than MSFT
        "MSFT": [{"date": f"{today_iso} 09:30:00-04:00", "close": 300.0}],
    }

    result = await portfolio_history.get_portfolio_history(_FakeDb(activities), "1D", _FakeFinnhub(prices))

    by_date = {p["date"]: p for p in result}
    point_930 = by_date[f"{today_iso} 09:30:00-04:00"]
    # 09:30 is before AAPL's own first bar — backfilled with AAPL's first
    # known price (150.0), not excluded, so this still includes both holdings.
    assert point_930["value"] == 8_000.0 + 10 * 150.0 + 5 * 300.0
    assert point_930["total_deposits_cad"] == 10_000.0  # constant all day, same snapshot as "value"
