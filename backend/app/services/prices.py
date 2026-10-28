"""Current prices for portfolio holdings (issue #19). Answers one question:
what is symbol X, in native currency Y, worth right now — from the right
source, with a short shared cache and a last-known-price fallback. Never
raises to the caller; every outcome is a PriceQuote."""

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Literal

import yfinance

from app.services.stocks import FinnhubClient

_log = logging.getLogger(__name__)

PRICE_SYMBOL_OVERRIDES: dict[str, str] = {}  # e.g. {"XYZ": "XYZ.NE"}
_CANADIAN_SUFFIXES = (".TO", ".V", ".NE", ".CN")
_PRICE_TTL_SECONDS = 15
# Positive cache: a good quote is reused this long, so /positions and /summary
# (and extra tabs) share one upstream call per symbol.
_FAILURE_TTL_SECONDS = 5
# Negative cache: a failed or withheld result (stale / unavailable /
# currency_mismatch) is reused this long, so a dead source is not retried by
# every request that arrives right behind the one that failed.

PriceStatus = Literal["ok", "stale", "unavailable", "currency_mismatch"]


@dataclass(frozen=True)
class PriceQuote:
    """One price lookup result, in the holding's native currency.

    status:
        ok                fresh quote
        stale             upstream failed; the last known good price is served
        unavailable       no price, and none was ever cached
        currency_mismatch yfinance reported a different currency than the
                          holding's native one (e.g. the US listing of a CDR);
                          the price is withheld, never shown

    currency is what the source reported — only yfinance reports one, so it is
    None for Finnhub quotes. fetched_at is when the price was fetched
    upstream, not when it was served: a stale quote keeps its original
    timestamp so callers can show how old it really is."""

    price: float | None
    currency: str | None
    fetched_at: datetime | None
    status: PriceStatus


def yfinance_symbol(symbol: str) -> str:
    """Quote symbol for a CAD-native holding. The activities export carries no
    exchange field, so this is a rule, not a lookup: an override wins, a symbol
    that already ends in a Canadian suffix (Wealthsimple writes e.g. 'RY.TO')
    is kept, and anything else (a bare CDR like 'AVGO') gets '.TO'. A symbol
    that lives only on another exchange needs an entry in the override map."""

    if symbol in PRICE_SYMBOL_OVERRIDES:
        return PRICE_SYMBOL_OVERRIDES[symbol]
    return symbol if symbol.upper().endswith(_CANADIAN_SUFFIXES) else f"{symbol}.TO"


class PriceService:
    """Created once in lifespan (app.state.prices) and shared by every request,
    which is why the cache and locks can live on the instance. Keys are
    (symbol, native_currency): the CAD-native CDR 'AVGO' and the USD stock
    'AVGO' are different keys with different sources.

    Three pieces of state work together (see .doc/keynotes.md, "Cache + lock +
    retry", and .doc/diagrams/price-cache-lock-sequence.html):

    _locks      who fetches. One lock per key: the first caller fetches, any
                caller arriving meanwhile waits, then reads what the first
                one stored. The lock never decides *whether* to retry; the
                cache check after acquiring it does.
    _cache      whether to fetch. The latest result per key with the moment it
                was stored. Positive entries (status ok) stay fresh for
                _PRICE_TTL_SECONDS; negative entries (stale, unavailable,
                currency_mismatch) for the shorter _FAILURE_TTL_SECONDS.
    _last_good  what to show when a fetch fails. Only ok quotes, never
                overwritten by a failure, so a stale answer always has a
                price to copy.

    Single uvicorn process assumed; with several workers each would hold its
    own cache and make its own upstream calls."""

    def __init__(self, finnhub: FinnhubClient) -> None:
        self._finnhub = finnhub  # re-use existing client
        self._cache: dict[tuple[str, str], tuple[PriceQuote, float]] = {}  # quote, time.monotonic()
        # e.g.
        #   {("AVGO", "USD"): (PriceQuote(price=335.38, currency=None,  fetched_at=14:00:00Z, status="ok"),    1042.7),
        #    "NVDA", "USD"): (PriceQuote(price=None,   currency=None,  fetched_at=None,      status="unavailable"), 1043.1)}
        self._last_good: dict[tuple[str, str], PriceQuote] = {}
        # e.g.
        #   {("AVGO", "USD"): PriceQuote(price=335.38, currency=None,  fetched_at=14:00:00Z, status="ok"),
        #    ("AVGO", "CAD"): PriceQuote(price=13.08,  currency="CAD", fetched_at=14:00:01Z, status="ok")}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        # e.g.
        #   {("AVGO", "USD"): <asyncio.Lock unlocked>,
        #    ("NVDA", "USD"): <asyncio.Lock unlocked>,
        #    ("AVGO", "CAD"): <asyncio.Lock locked>}

    def _is_fresh(self, key: tuple[str, str]) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        quote, stored_at = entry
        ttl = _PRICE_TTL_SECONDS if quote.status == "ok" else _FAILURE_TTL_SECONDS
        return time.monotonic() - stored_at < ttl

    async def get_price(self, symbol: str, native_currency: str) -> PriceQuote:
        """Quote for one holding. Never raises.

        1. fresh cache entry (good or failed): return it, no network call
        2. otherwise take the key's lock and look again; the caller ahead of us
           may have just filled the cache while we waited
        3. still nothing fresh: fetch. A good quote is cached for
           _PRICE_TTL_SECONDS and remembered as last good. A failure returns the
           last good quote marked stale (original fetched_at kept), or
           unavailable if there never was one, and is cached for the shorter
           _FAILURE_TTL_SECONDS. A currency_mismatch is returned as is, cached
           the same short time, and never becomes last good."""
        key = (symbol, native_currency)
        if self._is_fresh(key):
            return self._cache[key][0]

        async with self._locks.setdefault(key, asyncio.Lock()):
            if self._is_fresh(key):
                return self._cache[key][0]

            quote = await self._fetch(symbol, native_currency)
            if quote is None:
                last = self._last_good.get(key)
                quote = replace(last, status="stale") if last else PriceQuote(None, None, None, "unavailable")
            elif quote.status == "ok":
                self._last_good[key] = quote

            self._cache[key] = (quote, time.monotonic())
            return quote

    async def get_prices(self, pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], PriceQuote]:
        """Quotes for many holdings, keyed by (symbol, native_currency). This
        is the only method the routes call. Duplicate pairs are looked up once;
        different pairs run concurrently through get_price, so the cache, lock
        and stale fallback all still apply and the whole call takes about as
        long as the slowest source, not the sum. Never raises, because
        get_price never does."""
        keys = list(set(pairs))
        quotes = await asyncio.gather(*(self.get_price(s, c) for s, c in keys))
        return dict(zip(keys, quotes))

    async def _fetch(self, symbol: str, native_currency: str) -> PriceQuote | None:
        """One live lookup. None means the source fetch failed; the caller decides
        between a stale and an unavailable result."""
        now = datetime.now(timezone.utc)

        # use finnhub API to quote USD-native holdings
        if native_currency == "USD":
            price = await self._finnhub.get_price(symbol)
            return PriceQuote(price, None, now, "ok") if price else None

        # use yfinance to quote CAD-native holdings
        def _call() -> tuple[float | None, str | None]:
            fi = yfinance.Ticker(yfinance_symbol(symbol)).fast_info
            return fi["last_price"], fi["currency"]

        try:
            price, currency = await asyncio.get_running_loop().run_in_executor(None, _call)
        except Exception:
            _log.warning("yfinance quote failed for %s", symbol)
            return None
        if not price or price <= 0:
            return None
        if currency != native_currency:
            return PriceQuote(None, currency, now, "currency_mismatch")
        return PriceQuote(price, currency, now, "ok")
