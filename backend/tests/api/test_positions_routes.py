import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import positions
from app.core.db import get_db
from app.models.fx_rate import FxRate
from app.services.ledger_cache import LedgerCache, LedgerSnapshot
from app.services.ledger_errors import LedgerImportError
from app.services.portfolio import MergedHolding
from app.services.prices import PriceQuote, PriceService

AS_OF = datetime(2026, 10, 26, 14, 30, tzinfo=timezone.utc)
TRADED = datetime(2026, 7, 27, 14, 36, tzinfo=timezone.utc)


class _Ledger:
    """Stands in for LedgerCache: hands back a fixed snapshot, or raises."""

    def __init__(self, snapshot: LedgerSnapshot | None = None, error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.error = error

    async def get(self, _db):
        if self.error:
            raise self.error
        return self.snapshot


class _Prices:
    """Stands in for PriceService: records what was asked, answers from `quotes`."""

    def __init__(self, quotes: dict) -> None:
        self.quotes = quotes
        self.asked: set | None = None

    async def get_prices(self, pairs):
        self.asked = set(pairs)
        return self.quotes


class _Types:
    """Stands in for AssetTypeService: records what was asked, answers from `types`."""

    def __init__(self, types: dict | None = None) -> None:
        self.types = types or {}
        self.asked: set | None = None

    async def get_types(self, pairs):
        self.asked = set(pairs)
        return self.types


def _holding(symbol: str, currency: str, shares: float, avg_cost: float) -> MergedHolding:
    return MergedHolding(symbol, currency, shares, avg_cost, TRADED)


def _ok(price: float) -> PriceQuote:
    return PriceQuote(price, None, AS_OF, "ok")


class _Db:
    """Stands in for AsyncSession; the summary route only does db.get(FxRate, "USD")."""

    def __init__(self, usd_rate: FxRate | None = None) -> None:
        self.usd_rate = usd_rate
        self.gets: list[tuple] = []

    async def get(self, model, key):
        self.gets.append((model, key))
        return self.usd_rate


def _request(path: str, ledger: _Ledger, prices: _Prices, db: _Db | None = None, types: _Types | None = None):
    app = FastAPI()
    app.include_router(positions.router)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[positions.get_ledger_cache] = lambda: ledger
    app.dependency_overrides[positions.get_price_service] = lambda: prices
    app.dependency_overrides[positions.get_asset_type_service] = lambda: types or _Types()
    return TestClient(app, raise_server_exceptions=False).get(path)


def _get(ledger: _Ledger, prices: _Prices, types: _Types | None = None):
    return _request("/api/positions", ledger, prices, types=types)


def test_rows_are_sorted_by_market_value_with_unpriced_last() -> None:
    ledger = _Ledger(LedgerSnapshot((
        _holding("SOFI", "USD", 100, 8.0),    # no quote -> unpriced, must be last
        _holding("AAPL", "USD", 10, 100.0),   # 10 * 150 = 1500
        _holding("NVDA", "USD", 15, 110.0),   # 15 * 120 = 1800
    ), cash=0.0))
    prices = _Prices({("NVDA", "USD"): _ok(120.0), ("AAPL", "USD"): _ok(150.0)})

    response = _get(ledger, prices)

    assert response.status_code == 200
    assert [r["symbol"] for r in response.json()] == ["NVDA", "AAPL", "SOFI"]


def test_a_priced_row_carries_every_field_the_page_needs() -> None:
    ledger = _Ledger(LedgerSnapshot((_holding("NVDA", "USD", 15, 110.0),), cash=0.0))

    (row,) = _get(ledger, _Prices({("NVDA", "USD"): _ok(120.0)})).json()

    assert row == {
        "symbol": "NVDA", "native_currency": "USD",
        "shares": 15.0, "avg_cost": 110.0, "invested": 1650.0,
        "current_price": 120.0, "price_status": "ok",
        "price_as_of": "2026-10-26T14:30:00Z",
        "market_value": 1800.0, "unrealized_gain": 150.0,
        "unrealized_gain_pct": pytest.approx(150 / 1650),
        "last_traded_at": "2026-07-27T14:36:00Z",
        "asset_type": None,  # no type known: the key is present and null
    }


def test_asset_types_are_requested_and_returned_per_symbol_and_currency() -> None:
    ledger = _Ledger(LedgerSnapshot((
        _holding("AVGO", "USD", 5, 900.0),
        _holding("AVGO", "CAD", 20, 30.0),
    ), cash=0.0))
    prices = _Prices({("AVGO", "USD"): _ok(1000.0), ("AVGO", "CAD"): _ok(35.0)})
    types = _Types({("AVGO", "USD"): "Stock", ("AVGO", "CAD"): "CDR"})

    rows = _get(ledger, prices, types).json()

    assert types.asked == {("AVGO", "USD"), ("AVGO", "CAD")}
    assert {(r["native_currency"], r["asset_type"]) for r in rows} == {("USD", "Stock"), ("CAD", "CDR")}


def test_a_failed_type_lookup_leaves_the_price_fields_alone() -> None:
    ledger = _Ledger(LedgerSnapshot((_holding("NVDA", "USD", 15, 110.0),), cash=0.0))
    prices = _Prices({("NVDA", "USD"): _ok(120.0)})

    (plain,) = _get(ledger, prices).json()
    (typed,) = _get(ledger, prices, _Types({("NVDA", "USD"): None})).json()

    assert typed == plain
    assert typed["asset_type"] is None
    assert (typed["price_status"], typed["market_value"]) == ("ok", 1800.0)


async def test_prices_and_types_are_fetched_concurrently() -> None:
    # each side waits for the other to start, so a sequential load never finishes
    prices_started, types_started = asyncio.Event(), asyncio.Event()

    class _WaitingPrices:
        async def get_prices(self, pairs):
            prices_started.set()
            await types_started.wait()
            return {}

    class _WaitingTypes:
        async def get_types(self, pairs):
            types_started.set()
            await prices_started.wait()
            return {}

    ledger = _Ledger(LedgerSnapshot((_holding("NVDA", "USD", 1, 1.0),), cash=0.0))

    await asyncio.wait_for(positions._load_priced_rows(ledger, _WaitingPrices(), None, _WaitingTypes()), timeout=2)


def test_the_summary_does_not_look_up_types() -> None:
    ledger = _Ledger(LedgerSnapshot((_holding("NVDA", "USD", 15, 110.0),), cash=0.0))
    types = _Types({("NVDA", "USD"): "Stock"})

    response = _request("/api/portfolio/summary", ledger, _Prices({("NVDA", "USD"): _ok(120.0)}), _Db(), types)

    assert response.status_code == 200
    assert types.asked is None


def test_types_are_not_looked_up_for_a_ledger_we_cannot_trust() -> None:
    ledger = _Ledger(error=LedgerImportError("negative_cash", "cash went negative"))
    types = _Types()

    assert _get(ledger, _Prices({}), types).status_code == 500
    assert types.asked is None


def test_an_unpriced_row_is_still_returned_with_null_price_fields() -> None:
    ledger = _Ledger(LedgerSnapshot((_holding("SOFI", "USD", 100, 8.0),), cash=0.0))
    prices = _Prices({("SOFI", "USD"): PriceQuote(None, None, None, "unavailable")})

    (row,) = _get(ledger, prices).json()

    assert row["price_status"] == "unavailable"
    assert row["invested"] == 800.0  # cost does not depend on a price
    assert row["last_traded_at"] == "2026-07-27T14:36:00Z"  # nor does the date
    for field in ("current_price", "price_as_of", "market_value", "unrealized_gain", "unrealized_gain_pct"):
        assert row[field] is None  # the key is present and null, not missing


def test_prices_are_requested_for_each_symbol_and_native_currency() -> None:
    # the USD stock AVGO and the CAD CDR AVGO are two rows and two lookups
    ledger = _Ledger(LedgerSnapshot((
        _holding("AVGO", "USD", 5, 900.0),
        _holding("AVGO", "CAD", 20, 30.0),
    ), cash=0.0))
    prices = _Prices({("AVGO", "USD"): _ok(1000.0), ("AVGO", "CAD"): _ok(35.0)})

    response = _get(ledger, prices)

    assert prices.asked == {("AVGO", "USD"), ("AVGO", "CAD")}
    assert len(response.json()) == 2


def test_an_empty_ledger_is_an_empty_list_not_an_error() -> None:
    response = _get(_Ledger(LedgerSnapshot((), cash=0.0)), _Prices({}))

    assert response.status_code == 200
    assert response.json() == []


def test_a_failed_integrity_check_is_a_500_with_the_error_code() -> None:
    ledger = _Ledger(error=LedgerImportError("negative_cash", "cash went negative"))
    prices = _Prices({})

    response = _get(ledger, prices)

    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "negative_cash", "message": "cash went negative"}}
    assert prices.asked is None  # nothing was priced for a ledger we cannot trust


def test_the_dependencies_read_the_objects_lifespan_put_on_app_state() -> None:
    ledger, prices, types = LedgerCache(), object(), object()
    state = SimpleNamespace(ledger_cache=ledger, prices=prices, asset_types=types)
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    assert positions.get_ledger_cache(request) is ledger
    assert positions.get_price_service(request) is prices
    assert positions.get_asset_type_service(request) is types


def test_real_price_service_and_empty_pair_set_do_not_call_upstream() -> None:
    # PriceService with no holdings must answer {} without touching Finnhub
    # or yfinance; the finnhub client is a bare object that would blow up if used
    ledger = _Ledger(LedgerSnapshot((), cash=0.0))

    response = _get(ledger, PriceService(finnhub=object()))

    assert response.status_code == 200
    assert response.json() == []


def test_a_usd_row_is_priced_through_finnhub_without_subscribing() -> None:
    # Loading /portfolio must not open a Finnhub WebSocket subscription: that
    # is the alert system's job (and the free tier caps the symbols). Real
    # PriceService, fake Finnhub client, so the whole request path is covered.
    finnhub = SimpleNamespace(get_price=AsyncMock(return_value=190.0), subscribe=MagicMock())
    ledger = _Ledger(LedgerSnapshot((_holding("NVDA", "USD", 10, 100.0),), cash=0.0))

    response = _get(ledger, PriceService(finnhub))

    assert response.status_code == 200
    assert response.json()[0]["current_price"] == 190.0
    finnhub.get_price.assert_awaited_once_with("NVDA")
    finnhub.subscribe.assert_not_called()


# ---- GET /api/portfolio/summary -----------------------------------------

def _usd_rate(rate: float = 1.4, age: timedelta = timedelta(hours=1)) -> _Db:
    return _Db(FxRate(currency="USD", rate_to_cad=rate, fetched_at=datetime.now(timezone.utc) - age))


def _mixed() -> tuple[_Ledger, _Prices]:
    ledger = _Ledger(LedgerSnapshot((
        _holding("NVDA", "USD", 15, 110.0),  # cost 1650, worth 1800 USD
        _holding("XYZ", "CAD", 10, 20.0),    # cost 200, worth 250 CAD
    ), cash=500.0))
    return ledger, _Prices({("NVDA", "USD"): _ok(120.0), ("XYZ", "CAD"): _ok(25.0)})


def _summary(ledger: _Ledger, prices: _Prices, db: _Db):
    return _request("/api/portfolio/summary", ledger, prices, db)


def test_summary_totals_each_currency_and_converts_usd_at_todays_rate() -> None:
    ledger, prices = _mixed()

    response = _summary(ledger, prices, _usd_rate(1.4))

    assert response.status_code == 200
    assert response.json() == {
        "subtotals": [  # USD first, then CAD
            {"currency": "USD", "invested": 1650.0, "market_value": 1800.0, "unrealized_gain": 150.0,
             "unrealized_gain_pct": pytest.approx(150 / 1650), "holdings_count": 1, "unpriced_count": 0},
            {"currency": "CAD", "invested": 200.0, "market_value": 250.0, "unrealized_gain": 50.0,
             "unrealized_gain_pct": 0.25, "holdings_count": 1, "unpriced_count": 0},
        ],
        "cash_cad": 500.0,
        "balance_cad": 250.0 + 1800.0 * 1.4 + 500.0,  # CAD value + USD value x rate + cash = 3270
        "fx_available": True,
        "fx_stale": False,
        "unpriced_count": 0,
    }


def test_summary_looks_up_the_usd_row_of_fx_rates() -> None:
    db = _usd_rate()

    _summary(*_mixed(), db)

    assert db.gets == [(FxRate, "USD")]


def test_a_rate_over_24_hours_old_is_still_used_but_flagged_stale() -> None:
    body = _summary(*_mixed(), _usd_rate(1.4, age=timedelta(hours=30))).json()

    assert body["fx_stale"] is True
    assert body["fx_available"] is True
    assert body["balance_cad"] == 250.0 + 1800.0 * 1.4 + 500.0


def test_a_rate_under_24_hours_old_is_not_stale() -> None:
    assert _summary(*_mixed(), _usd_rate(age=timedelta(hours=23))).json()["fx_stale"] is False


def test_no_usd_rate_with_a_priced_usd_holding_gives_no_balance_but_keeps_the_subtotals() -> None:
    body = _summary(*_mixed(), _Db(None)).json()

    assert body["balance_cad"] is None
    assert body["fx_available"] is False
    assert body["fx_stale"] is False
    assert [s["currency"] for s in body["subtotals"]] == ["USD", "CAD"]  # per-currency figures survive


def test_a_cad_only_ledger_needs_no_rate() -> None:
    ledger = _Ledger(LedgerSnapshot((_holding("XYZ", "CAD", 10, 20.0),), cash=500.0))
    prices = _Prices({("XYZ", "CAD"): _ok(25.0)})

    body = _summary(ledger, prices, _Db(None)).json()

    assert body["balance_cad"] == 750.0
    assert body["fx_available"] is True


def test_an_unpriced_usd_holding_is_counted_and_does_not_need_a_rate() -> None:
    ledger = _Ledger(LedgerSnapshot((_holding("SOFI", "USD", 100, 8.0),), cash=500.0))
    prices = _Prices({("SOFI", "USD"): PriceQuote(None, None, None, "unavailable")})

    body = _summary(ledger, prices, _Db(None)).json()

    assert body["unpriced_count"] == 1
    assert body["balance_cad"] == 500.0  # nothing priced to convert, so the rate is irrelevant
    assert body["fx_available"] is True
    assert body["subtotals"][0]["invested"] == 800.0


def test_an_empty_ledger_summary_is_zero_not_an_error() -> None:
    body = _summary(_Ledger(LedgerSnapshot((), cash=0.0)), _Prices({}), _Db(None)).json()

    assert body == {"subtotals": [], "cash_cad": 0.0, "balance_cad": 0.0,
                    "fx_available": True, "fx_stale": False, "unpriced_count": 0}


def test_summary_integrity_failure_is_a_500_with_the_error_code() -> None:
    ledger = _Ledger(error=LedgerImportError("negative_cash", "cash went negative"))
    prices = _Prices({})

    response = _summary(ledger, prices, _Db(None))

    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "negative_cash", "message": "cash went negative"}}
    assert prices.asked is None
