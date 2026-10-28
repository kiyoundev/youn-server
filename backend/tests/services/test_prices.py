import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import prices
from app.services.prices import PriceService, yfinance_symbol


class _Clock:
    """Stands in for the `time` module inside prices.py so TTL tests do not
    wait. Patched on the prices module only; asyncio keeps the real clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeYFinance:
    """Stands in for the yfinance module: Ticker(symbol).fast_info is a dict
    the test controls. `error` makes Ticker() raise, like a Yahoo failure."""

    def __init__(self) -> None:
        self.fast_info: dict = {"last_price": 13.08, "currency": "CAD"}
        self.error: Exception | None = None
        self.symbols: list[str] = []

    def Ticker(self, symbol: str):  # noqa: N802 - mirrors yfinance.Ticker
        self.symbols.append(symbol)
        if self.error:
            raise self.error
        return SimpleNamespace(fast_info=self.fast_info)


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(prices, "time", SimpleNamespace(monotonic=c.monotonic))
    return c


@pytest.fixture
def yf(monkeypatch) -> _FakeYFinance:
    fake = _FakeYFinance()
    monkeypatch.setattr(prices, "yfinance", fake)
    return fake


@pytest.fixture
def finnhub() -> MagicMock:
    client = MagicMock()
    client.get_price = AsyncMock(return_value=335.38)
    return client


@pytest.fixture
def service(finnhub, yf, clock) -> PriceService:
    return PriceService(finnhub)


# --- yfinance_symbol -------------------------------------------------------


def test_bare_symbol_gets_to_suffix() -> None:
    assert yfinance_symbol("AVGO") == "AVGO.TO"


@pytest.mark.parametrize("symbol", ["RY.TO", "XYZ.NE", "ABC.V", "DEF.CN", "ry.to"])
def test_existing_canadian_suffix_is_kept(symbol: str) -> None:
    assert yfinance_symbol(symbol) == symbol


def test_override_beats_the_suffix_rule(monkeypatch) -> None:
    monkeypatch.setitem(prices.PRICE_SYMBOL_OVERRIDES, "AVGO", "AVGO.NE")
    assert yfinance_symbol("AVGO") == "AVGO.NE"


# --- _fetch: routing -------------------------------------------------------


async def test_usd_goes_to_finnhub_only(service, finnhub, yf) -> None:
    quote = await service._fetch("AVGO", "USD")

    assert (quote.status, quote.price, quote.currency) == ("ok", 335.38, None)
    assert quote.fetched_at is not None
    finnhub.get_price.assert_awaited_once_with("AVGO")
    finnhub.subscribe.assert_not_called()
    assert yf.symbols == []


async def test_cad_goes_to_yfinance_only(service, finnhub, yf) -> None:
    quote = await service._fetch("AVGO", "CAD")

    assert (quote.status, quote.price, quote.currency) == ("ok", 13.08, "CAD")
    assert yf.symbols == ["AVGO.TO"]
    finnhub.get_price.assert_not_called()


# --- _fetch: failures ------------------------------------------------------


async def test_currency_mismatch_withholds_the_price(service, yf) -> None:
    # the US listing of a CDR: ~344 USD must never be shown as a CAD price
    yf.fast_info = {"last_price": 344.0, "currency": "USD"}

    quote = await service._fetch("AVGO", "CAD")

    assert (quote.status, quote.price, quote.currency) == ("currency_mismatch", None, "USD")


@pytest.mark.parametrize("last_price", [None, 0, -1.0])
async def test_unusable_yfinance_price_is_a_failure(service, yf, last_price) -> None:
    yf.fast_info = {"last_price": last_price, "currency": "CAD"}

    assert await service._fetch("AVGO", "CAD") is None


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("last_price")])
async def test_yfinance_exception_is_a_failure(service, yf, error) -> None:
    yf.error = error

    assert await service._fetch("AVGO", "CAD") is None


async def test_finnhub_none_is_a_failure(service, finnhub) -> None:
    finnhub.get_price.return_value = None

    assert await service._fetch("AVGO", "USD") is None


# --- get_price: positive cache ---------------------------------------------


async def test_ok_quote_is_reused_until_the_ttl(service, finnhub, clock) -> None:
    await service.get_price("AVGO", "USD")
    clock.advance(prices._PRICE_TTL_SECONDS / 2)
    await service.get_price("AVGO", "USD")
    assert finnhub.get_price.await_count == 1

    clock.advance(prices._PRICE_TTL_SECONDS)  # now past the TTL
    await service.get_price("AVGO", "USD")
    assert finnhub.get_price.await_count == 2


async def test_same_symbol_in_two_currencies_is_two_entries(service, finnhub, yf) -> None:
    us = await service.get_price("AVGO", "USD")
    cdr = await service.get_price("AVGO", "CAD")

    assert (us.price, cdr.price) == (335.38, 13.08)
    finnhub.get_price.assert_awaited_once_with("AVGO")
    assert yf.symbols == ["AVGO.TO"]


# --- get_price: lock -------------------------------------------------------


async def test_concurrent_calls_for_one_key_fetch_once(service, finnhub) -> None:
    async def slow(symbol: str) -> float:
        await asyncio.sleep(0.01)
        return 335.38

    finnhub.get_price.side_effect = slow

    quotes = await asyncio.gather(*(service.get_price("AVGO", "USD") for _ in range(3)))

    assert finnhub.get_price.await_count == 1
    assert [q.status for q in quotes] == ["ok", "ok", "ok"]


async def test_different_keys_are_fetched_at_the_same_time(service, finnhub) -> None:
    # each fetch waits until both are in flight; a lock shared across keys
    # would never let the second start, and wait_for would time out
    entered: list[str] = []
    both_in_flight = asyncio.Event()

    async def rendezvous(symbol: str) -> float:
        entered.append(symbol)
        if len(entered) == 2:
            both_in_flight.set()
        await asyncio.wait_for(both_in_flight.wait(), timeout=1)
        return 100.0

    finnhub.get_price.side_effect = rendezvous

    quotes = await asyncio.gather(
        service.get_price("AVGO", "USD"), service.get_price("NVDA", "USD")
    )

    assert [q.status for q in quotes] == ["ok", "ok"]


# --- get_price: failure path and negative cache ----------------------------


async def test_failure_after_success_serves_the_old_price_as_stale(
    service, finnhub, clock
) -> None:
    finnhub.get_price.side_effect = [335.38, None]
    first = await service.get_price("AVGO", "USD")

    clock.advance(prices._PRICE_TTL_SECONDS + 1)
    second = await service.get_price("AVGO", "USD")

    assert second.status == "stale"
    assert second.price == 335.38
    assert second.fetched_at == first.fetched_at  # shows how old the price really is


async def test_failure_with_no_history_is_unavailable(service, finnhub) -> None:
    finnhub.get_price.return_value = None

    quote = await service.get_price("NVDA", "USD")

    assert (quote.status, quote.price, quote.fetched_at) == ("unavailable", None, None)


async def test_failure_is_not_retried_inside_the_failure_ttl(
    service, finnhub, clock
) -> None:
    finnhub.get_price.return_value = None

    await service.get_price("NVDA", "USD")
    clock.advance(prices._FAILURE_TTL_SECONDS / 2)
    await service.get_price("NVDA", "USD")
    assert finnhub.get_price.await_count == 1

    clock.advance(prices._FAILURE_TTL_SECONDS)  # window over, the source is asked again
    await service.get_price("NVDA", "USD")
    assert finnhub.get_price.await_count == 2


async def test_success_after_stale_replaces_it(service, finnhub, clock) -> None:
    finnhub.get_price.side_effect = [335.38, None, 340.0]
    await service.get_price("AVGO", "USD")
    clock.advance(prices._PRICE_TTL_SECONDS + 1)
    assert (await service.get_price("AVGO", "USD")).status == "stale"

    clock.advance(prices._FAILURE_TTL_SECONDS + 1)
    recovered = await service.get_price("AVGO", "USD")

    assert (recovered.status, recovered.price) == ("ok", 340.0)


async def test_currency_mismatch_never_becomes_the_last_good_quote(
    service, yf, clock
) -> None:
    yf.fast_info = {"last_price": 344.0, "currency": "USD"}
    first = await service.get_price("AVGO", "CAD")
    assert first.status == "currency_mismatch"

    # served from the short negative cache, no second yfinance call
    clock.advance(prices._FAILURE_TTL_SECONDS / 2)
    await service.get_price("AVGO", "CAD")
    assert len(yf.symbols) == 1

    # a later outright failure has no good price to fall back to
    clock.advance(prices._FAILURE_TTL_SECONDS)
    yf.error = RuntimeError("down")
    second = await service.get_price("AVGO", "CAD")
    assert (second.status, second.price) == ("unavailable", None)


# --- get_prices ------------------------------------------------------------


async def test_get_prices_batches_and_dedupes(service, finnhub) -> None:
    async def by_symbol(symbol: str) -> float | None:
        return None if symbol == "BAD" else 100.0

    finnhub.get_price.side_effect = by_symbol

    result = await service.get_prices(
        [("AVGO", "USD"), ("NVDA", "USD"), ("AVGO", "USD"), ("BAD", "USD")]
    )

    assert finnhub.get_price.await_count == 3  # the duplicate AVGO is looked up once
    assert {k: q.status for k, q in result.items()} == {
        ("AVGO", "USD"): "ok",
        ("NVDA", "USD"): "ok",
        ("BAD", "USD"): "unavailable",
    }


async def test_get_prices_with_no_pairs_is_empty(service) -> None:
    assert await service.get_prices([]) == {}
