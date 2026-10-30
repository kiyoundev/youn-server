import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.services import asset_types
from app.services.asset_types import AssetTypeService


class _Clock:
    """Stands in for the `time` module inside asset_types.py so the retry
    window needs no waiting. asyncio keeps the real clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeYFinance:
    """Stands in for the yfinance module. `table` maps a Yahoo symbol to what
    Yahoo knows about it; a symbol missing from the table raises, like a
    delisted ticker. `error` makes every Ticker() raise."""

    def __init__(self) -> None:
        self.table: dict[str, dict] = {}
        self.error: Exception | None = None
        self.info_error: Exception | None = None
        self.symbols: list[str] = []
        self.info_calls = 0
        self.gate: threading.Event | None = None  # when set, Ticker() blocks until it is released

    def Ticker(self, symbol: str):  # noqa: N802 - mirrors yfinance.Ticker
        self.symbols.append(symbol)
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.error:
            raise self.error
        record = self.table[symbol]
        fake = self

        class _Ticker:
            fast_info = {"quote_type": record.get("quote_type")}

            @property
            def info(self) -> dict:
                fake.info_calls += 1
                if fake.info_error:
                    raise fake.info_error
                return {k: v for k, v in record.items() if k == "shortName"}

        return _Ticker()


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(asset_types, "time", SimpleNamespace(monotonic=c.monotonic))
    return c


@pytest.fixture
def yf(monkeypatch) -> _FakeYFinance:
    fake = _FakeYFinance()
    fake.table = {
        "NVDA": {"quote_type": "EQUITY"},
        "SPY": {"quote_type": "ETF"},
        "RY.TO": {"quote_type": "EQUITY"},
        "XIU.TO": {"quote_type": "ETF", "shortName": "iSHARES SP TSX 60 INDEX ETF"},
        "AVGO.TO": {"quote_type": "ETF", "shortName": "BROADCOM CDR (CAD HEDGED)"},
    }
    monkeypatch.setattr(asset_types, "yfinance", fake)
    return fake


@pytest.fixture
def service(yf, clock) -> AssetTypeService:
    return AssetTypeService()


# --- mapping ---------------------------------------------------------------


async def test_usd_equity_is_a_stock_looked_up_by_its_own_symbol(service, yf) -> None:
    assert await service.get_type("NVDA", "USD") == "Stock"
    assert yf.symbols == ["NVDA"]  # no .TO suffix for a USD holding
    assert yf.info_calls == 0


async def test_usd_etf_is_an_etf_without_the_name_lookup(service, yf) -> None:
    assert await service.get_type("SPY", "USD") == "ETF"
    assert yf.info_calls == 0  # a USD ETF is never a CDR


async def test_cad_equity_is_a_stock_on_the_toronto_symbol(service, yf) -> None:
    assert await service.get_type("RY.TO", "CAD") == "Stock"
    assert yf.symbols == ["RY.TO"]
    assert yf.info_calls == 0


async def test_cad_etf_without_cdr_in_its_name_is_an_etf(service, yf) -> None:
    assert await service.get_type("XIU.TO", "CAD") == "ETF"
    assert yf.info_calls == 1


async def test_cad_etf_with_cdr_in_its_name_is_a_cdr_found_via_the_to_suffix(service, yf) -> None:
    assert await service.get_type("AVGO", "CAD") == "CDR"
    assert yf.symbols == ["AVGO.TO"]


@pytest.mark.parametrize("name", ["Broadcom cdr (cad hedged)", "CDR", "TSX CDR FUND"])
async def test_cdr_match_ignores_case(service, yf, name) -> None:
    yf.table["AVGO.TO"]["shortName"] = name
    assert await service.get_type("AVGO", "CAD") == "CDR"


@pytest.mark.parametrize("name", ["ACDRX INCOME FUND", "SECDR ETF", None, ""])
async def test_cdr_must_be_a_whole_word(service, yf, name) -> None:
    yf.table["AVGO.TO"]["shortName"] = name
    assert await service.get_type("AVGO", "CAD") == "ETF"


@pytest.mark.parametrize("quote_type", ["INDEX", "MUTUALFUND", "CRYPTOCURRENCY", "FUTURE"])
async def test_other_yahoo_types_get_no_badge_and_are_not_a_failure(service, yf, clock, quote_type) -> None:
    yf.table["NVDA"]["quote_type"] = quote_type

    assert await service.get_type("NVDA", "USD") is None
    clock.advance(10_000)
    assert await service.get_type("NVDA", "USD") is None
    assert yf.symbols == ["NVDA"]  # a real answer, so it is kept like any success


# --- failures --------------------------------------------------------------


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("quote_type")])
async def test_yfinance_exception_gives_none(service, yf, error) -> None:
    yf.error = error
    assert await service.get_type("NVDA", "USD") is None


async def test_unknown_symbol_gives_none(service) -> None:
    assert await service.get_type("NOPE", "USD") is None


@pytest.mark.parametrize("quote_type", [None, ""])
async def test_missing_quote_type_is_a_failure_that_is_retried(service, yf, clock, quote_type) -> None:
    yf.table["NVDA"]["quote_type"] = quote_type
    assert await service.get_type("NVDA", "USD") is None

    yf.table["NVDA"]["quote_type"] = "EQUITY"  # Yahoo recovers
    clock.advance(301)
    assert await service.get_type("NVDA", "USD") == "Stock"


async def test_failed_name_lookup_does_not_downgrade_a_cdr_to_etf(service, yf, clock) -> None:
    yf.info_error = RuntimeError("boom")
    assert await service.get_type("AVGO", "CAD") is None

    yf.info_error = None
    clock.advance(301)
    assert await service.get_type("AVGO", "CAD") == "CDR"


async def test_slow_lookup_times_out_to_none(service, yf, monkeypatch) -> None:
    monkeypatch.setattr(asset_types, "_LOOKUP_TIMEOUT_SECONDS", 0.05)
    yf.gate = threading.Event()
    try:
        assert await service.get_type("NVDA", "USD") is None
    finally:
        yf.gate.set()  # release the executor thread


# --- cache -----------------------------------------------------------------


async def test_success_is_kept_for_the_process(service, yf, clock) -> None:
    assert await service.get_type("NVDA", "USD") == "Stock"
    clock.advance(10 * 24 * 3600)
    assert await service.get_type("NVDA", "USD") == "Stock"
    assert yf.symbols == ["NVDA"]


async def test_failure_is_not_retried_for_five_minutes_then_recovers(service, yf, clock) -> None:
    yf.error = RuntimeError("boom")
    assert await service.get_type("NVDA", "USD") is None

    yf.error = None
    clock.advance(299)
    assert await service.get_type("NVDA", "USD") is None
    assert yf.symbols == ["NVDA"]  # served from the negative cache

    clock.advance(2)
    assert await service.get_type("NVDA", "USD") == "Stock"
    assert yf.symbols == ["NVDA", "NVDA"]

    clock.advance(10_000)
    assert await service.get_type("NVDA", "USD") == "Stock"
    assert yf.symbols == ["NVDA", "NVDA"]  # and now it is kept


async def test_concurrent_first_requests_make_one_lookup(service, yf) -> None:
    results = await asyncio.gather(*(service.get_type("NVDA", "USD") for _ in range(5)))

    assert results == ["Stock"] * 5
    assert yf.symbols == ["NVDA"]


async def test_usd_and_cad_with_the_same_symbol_are_different_keys(service, yf) -> None:
    yf.table["AVGO"] = {"quote_type": "EQUITY"}  # the US stock

    assert await service.get_type("AVGO", "USD") == "Stock"
    assert await service.get_type("AVGO", "CAD") == "CDR"


# --- get_types -------------------------------------------------------------


async def test_get_types_returns_every_pair_and_looks_up_duplicates_once(service, yf) -> None:
    result = await service.get_types(
        [("NVDA", "USD"), ("AVGO", "CAD"), ("NVDA", "USD"), ("RY.TO", "CAD")]
    )

    assert result == {("NVDA", "USD"): "Stock", ("AVGO", "CAD"): "CDR", ("RY.TO", "CAD"): "Stock"}
    assert sorted(yf.symbols) == ["AVGO.TO", "NVDA", "RY.TO"]


async def test_one_failing_pair_does_not_affect_the_others(service) -> None:
    result = await service.get_types([("NVDA", "USD"), ("NOPE", "USD")])

    assert result == {("NVDA", "USD"): "Stock", ("NOPE", "USD"): None}


async def test_empty_input_gives_empty_dict(service) -> None:
    assert await service.get_types([]) == {}
