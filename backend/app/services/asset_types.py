"""What kind of security a holding is — Stock, ETF or CDR (issue #19). Kept out
of PriceService on purpose: a security's type never changes, while a price
expires in 15 seconds, and a slow or failed type lookup must never touch a
row's price. Never raises to the caller; every outcome is a type or None
(None = unknown, so the page shows no badge)."""

import asyncio
import logging
import re
import time
from collections.abc import Iterable
from typing import Literal

import yfinance

from app.services.prices import yfinance_symbol

_log = logging.getLogger(__name__)

AssetType = Literal["Stock", "ETF", "CDR"]

_LOOKUP_TIMEOUT_SECONDS = 5
_FAILURE_TTL_SECONDS = 300
# Negative cache: a failed lookup is retried after this long. A success is kept
# for the life of the process, because a security's type does not change.

_BY_QUOTE_TYPE: dict[str, AssetType] = {"EQUITY": "Stock", "ETF": "ETF"}
# Yahoo's other types (INDEX, MUTUALFUND, ...) are not something the activities
# export can contain, so they get no badge rather than a wrong one.
_CDR_IN_NAME = re.compile(r"\bCDR\b", re.IGNORECASE)


def _lookup(symbol: str, native_currency: str) -> AssetType | None:
    """One blocking yfinance lookup (run it in an executor). Raises when Yahoo
    gives no usable answer, so the caller can tell a failure from a type that
    simply has no badge.

    Yahoo files a CDR under quote type ETF, with no fund data, so the only
    tell is the name: a CAD-native ETF whose shortName contains the word CDR
    is a CDR (checked for AVGO.TO: 'BROADCOM CDR (CAD HEDGED)'). A USD ETF is
    never a CDR, so it skips the extra .info call."""
    quote_symbol = symbol if native_currency == "USD" else yfinance_symbol(symbol)
    ticker = yfinance.Ticker(quote_symbol)

    quote_type = ticker.fast_info["quote_type"]
    if not quote_type:
        raise LookupError(f"no quote type for {quote_symbol}")

    asset_type = _BY_QUOTE_TYPE.get(quote_type)
    if asset_type == "ETF" and native_currency == "CAD":
        if _CDR_IN_NAME.search(ticker.info.get("shortName") or ""):
            return "CDR"
    return asset_type


class AssetTypeService:
    """Created once in lifespan (app.state.asset_types) and shared by every
    request, which is why the cache and locks can live on the instance. Keys
    are (symbol, native_currency), as in PriceService: the USD stock 'AVGO'
    and the CAD-native CDR 'AVGO' are different securities.

    _cache  (type, expires_at). expires_at is None for a success (kept for the
            process) or a time.monotonic() deadline for a failure.
    _locks  one per key, so concurrent first requests make one lookup and the
            rest read what it stored.

    Single uvicorn process assumed, as for the other caches."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[AssetType | None, float | None]] = {}
        # e.g.
        #   {("AVGO", "CAD"): ("CDR", None),
        #    ("NVDA", "USD"): ("Stock", None),
        #    ("SOFI", "USD"): (None, 1342.7)}   # failed; retry once the clock passes 1342.7
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _is_fresh(self, key: tuple[str, str]) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        expires_at = entry[1]
        return expires_at is None or time.monotonic() < expires_at

    async def get_type(self, symbol: str, native_currency: str) -> AssetType | None:
        """Type of one holding, or None. Never raises.

        1. fresh cache entry (success or failure): return it, no network call
        2. otherwise take the key's lock and look again; the caller ahead of us
           may have just filled the cache while we waited
        3. still nothing fresh: look it up, giving Yahoo _LOOKUP_TIMEOUT_SECONDS.
           A success is kept for the process; any failure or timeout returns
           None and is remembered for _FAILURE_TTL_SECONDS."""
        key = (symbol, native_currency)
        if self._is_fresh(key):
            return self._cache[key][0]

        async with self._locks.setdefault(key, asyncio.Lock()):
            if self._is_fresh(key):
                return self._cache[key][0]

            try:
                asset_type = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(None, _lookup, symbol, native_currency),
                    _LOOKUP_TIMEOUT_SECONDS,
                )
            except Exception:
                # A timed-out lookup keeps running in its executor thread until
                # Yahoo answers; its result is dropped.
                _log.warning("asset type lookup failed for %s (%s)", symbol, native_currency)
                self._cache[key] = (None, time.monotonic() + _FAILURE_TTL_SECONDS)
                return None

            self._cache[key] = (asset_type, None)
            return asset_type

    async def get_types(self, pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], AssetType | None]:
        """Types for many holdings, keyed by (symbol, native_currency). Duplicate
        pairs are looked up once; different pairs run concurrently, so the call
        takes about as long as the slowest lookup. Never raises, because
        get_type never does."""
        keys = list(set(pairs))
        types = await asyncio.gather(*(self.get_type(s, c) for s, c in keys))
        return dict(zip(keys, types))
