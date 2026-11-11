import asyncio
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import httpx
import websockets
import yfinance as yf
from sqlalchemy import select

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.models.event import Event
from app.models.stock_alert import StockAlert

_log = logging.getLogger(__name__)

_FINNHUB_WS_URL = "wss://ws.finnhub.io"
_FINNHUB_REST_URL = "https://finnhub.io/api/v1"
_RECONNECT_INITIAL = 1.0
_RECONNECT_MAX = 60.0

DateRange = Literal["1D", "1W", "1M", "3M", "6M", "YTD", "ALL"]

# (yfinance period, interval) per range (schema.md). Interval decides whether
# get_price_history's returned date keeps a time component (intraday) or not.
_RANGE_TO_YFINANCE: dict[DateRange, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "1h"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "YTD": ("ytd", "1d"),
    "ALL": ("max", "1mo"),
}
_INTRADAY_INTERVALS = {"5m", "1h"}


def is_intraday_range(range_: DateRange) -> bool:
    """Whether get_price_history's date field keeps a time component for this
    range — true for any range whose resolved interval is sub-daily (1D and
    1W, currently), regardless of whether the range's own output granularity
    is itself daily (1W's chart points are one-per-day even though its
    source bars are hourly — portfolio_history.py collapses that gap)."""
    return _RANGE_TO_YFINANCE[range_][1] in _INTRADAY_INTERVALS


@dataclass
class _AlertState:
    id: int
    target_price: float
    direction: str  # "above" or "below"
    alert_type: str  # "buy_signal", "stop_loss", or "take_profit"
    alerted_at: datetime | None


class FinnhubClient:
    def __init__(self, event_queue: asyncio.Queue) -> None:
        self._queue = event_queue
        self._cache: dict[str, list[_AlertState]] = {}
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._listener_task: asyncio.Task | None = None
        self._pending_tasks: set[asyncio.Task] = set()

    @property
    def _enabled(self) -> bool:
        return bool(settings.finnhub_api_key)

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def start(self) -> None:
        if not self._enabled:
            _log.warning("FINNHUB_API_KEY not set — FinnhubClient disabled")
            return
        if self._listener_task:
            _log.warning("FinnhubClient already started")
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(StockAlert).where(StockAlert.active == True))
            for alert in result.scalars().all():
                self._add_to_cache(alert)

        self._listener_task = asyncio.create_task(self._listen())
        _log.info("FinnhubClient started with %d tickers", len(self._cache))

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        _log.info("FinnhubClient stopped")

    def add_alert(self, alert: StockAlert) -> None:
        existing = self._cache.get(alert.ticker, [])
        if any(a.id == alert.id for a in existing):
            return
        is_new_ticker = not existing
        self._add_to_cache(alert)
        if is_new_ticker:
            self._schedule(self._send_subscribe(alert.ticker))

    def remove_alert(self, alert_id: int, ticker: str) -> None:
        alerts = self._cache.get(ticker, [])
        self._cache[ticker] = [a for a in alerts if a.id != alert_id]
        if not self._cache[ticker]:
            del self._cache[ticker]
            self._schedule(self._send_unsubscribe(ticker))

    def update_alert(self, alert: StockAlert) -> None:
        for state in self._cache.get(alert.ticker, []):
            if state.id == alert.id:
                state.target_price = alert.target_price
                state.direction = alert.direction
                state.alert_type = alert.alert_type
                state.alerted_at = alert.alerted_at
                return

    def cached_tickers(self) -> list[str]:
        return list(self._cache)

    async def check_threshold(self, ticker: str, price: float) -> None:
        await self._check_threshold(ticker, price)

    def _add_to_cache(self, alert: StockAlert) -> None:
        state = _AlertState(
            id=alert.id,
            target_price=alert.target_price,
            direction=alert.direction,
            alert_type=alert.alert_type,
            alerted_at=alert.alerted_at,
        )
        self._cache.setdefault(alert.ticker, []).append(state)

    def _schedule(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _send_subscribe(self, ticker: str) -> None:
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "subscribe", "symbol": ticker}))
            except Exception:
                _log.warning("Subscribe failed for %s", ticker, exc_info=True)

    async def _send_unsubscribe(self, ticker: str) -> None:
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "unsubscribe", "symbol": ticker}))
            except Exception:
                _log.warning("Unsubscribe failed for %s", ticker, exc_info=True)

    async def _listen(self) -> None:
        backoff = _RECONNECT_INITIAL
        # The WebSocket takes the token only as a query param (a header gets a 401
        # here, unlike the REST quote in get_price). Keep it in the URL.
        url = f"{_FINNHUB_WS_URL}?token={settings.finnhub_api_key}"
        while True:
            try:
                async with websockets.connect(url) as ws:
                    self._ws = ws
                    backoff = _RECONNECT_INITIAL
                    _log.info("Finnhub WS connected; subscribing %d tickers", len(self._cache))
                    for ticker in list(self._cache):
                        await self._send_subscribe(ticker)
                    async for raw in ws:
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ws = None
                _log.warning("Finnhub WS disconnected; reconnecting in %.0fs", backoff, exc_info=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RECONNECT_MAX)

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "trade":
            return
        for trade in msg.get("data", []):
            ticker = trade.get("s")
            price = trade.get("p")
            if ticker and price is not None:
                try:
                    await self._check_threshold(ticker, float(price))
                except Exception:
                    _log.error("Threshold check failed for %s @ %.4f", ticker, float(price), exc_info=True)

    async def _check_threshold(self, ticker: str, price: float) -> None:
        alerts = self._cache.get(ticker)
        if not alerts:
            return
        now = datetime.now(timezone.utc)
        for state in alerts:
            crossed = (state.direction == "above" and price >= state.target_price) or (
                state.direction == "below" and price <= state.target_price
            )
            recovered = (state.direction == "above" and price < state.target_price) or (
                state.direction == "below" and price > state.target_price
            )
            if crossed and state.alerted_at is None:
                try:
                    await self._fire_event(state, ticker, price, now)
                    state.alerted_at = now
                except Exception:
                    _log.error("Failed to fire event for %s @ %.4f", ticker, price, exc_info=True)
            elif recovered and state.alerted_at is not None:
                try:
                    await self._clear_alerted_at(state.id)
                    state.alerted_at = None
                except Exception:
                    _log.error("Failed to clear alerted_at for alert %d", state.id, exc_info=True)

    async def _fire_event(self, state: _AlertState, ticker: str, price: float, now: datetime) -> None:
        payload = {
            "alert_id": state.id,
            "ticker": ticker,
            "price": price,
            "target_price": state.target_price,
            "direction": state.direction,
            "alert_type": state.alert_type,
        }
        async with AsyncSessionLocal() as session:
            async with session.begin():
                event = Event(type="STOCK_THRESHOLD", payload=payload, status="pending")
                session.add(event)
                alert_row = await session.get(StockAlert, state.id)
                if alert_row:
                    alert_row.last_price = price
                    alert_row.alerted_at = now
        await self._queue.put(event.id)
        _log.info(
            "STOCK_THRESHOLD fired: %s @ %.4f (target %.4f %s, %s)",
            ticker,
            price,
            state.target_price,
            state.direction,
            state.alert_type,
        )

    async def _clear_alerted_at(self, alert_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                alert_row = await session.get(StockAlert, alert_id)
                if alert_row:
                    alert_row.alerted_at = None

    async def get_price(self, ticker: str) -> float | None:
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Header, not a ?token= param: httpx puts the request URL in
                # its error messages, which this module logs on failure.
                resp = await client.get(
                    f"{_FINNHUB_REST_URL}/quote",
                    params={"symbol": ticker},
                    headers={"X-Finnhub-Token": settings.finnhub_api_key},
                )
            resp.raise_for_status()
            price = resp.json().get("c")
            return float(price) if price else None
        except Exception:
            _log.warning("Finnhub REST quote failed for %s", ticker, exc_info=True)
            return None

    async def validate_ticker(self, ticker: str) -> bool:
        return await self.get_price(ticker) is not None

    async def get_price_history(self, ticker: str, range_: DateRange, native_currency: Literal["USD", "CAD"] | None = None) -> list[dict]:
        # local import: prices.py imports FinnhubClient from this module
        from app.services.prices import yfinance_symbol

        period, interval = _RANGE_TO_YFINANCE[range_]
        query_symbol = yfinance_symbol(ticker) if native_currency == "CAD" else ticker
        intraday = interval in _INTRADAY_INTERVALS
        loop = asyncio.get_running_loop()
        try:

            def _fetch() -> list[dict]:
                hist = yf.Ticker(query_symbol).history(period=period, interval=interval)
                points: list[dict] = []
                for idx, row in hist.iterrows():
                    close = float(row["Close"])
                    if not math.isfinite(close):
                        # yfinance reports NaN for a bar with no actual trade
                        # (a halted symbol, a holiday gap) — treat it as no
                        # data for that bar, same as a missing date elsewhere
                        # in this pipeline, not a real price. Unfiltered, it
                        # reaches json.dumps(allow_nan=False) downstream and
                        # 500s the whole response.
                        continue
                    points.append({"date": str(idx) if intraday else str(idx.date()), "close": close})
                return points

            return await loop.run_in_executor(None, _fetch)
        except Exception:
            _log.warning("yfinance history failed for %s %s", query_symbol, range_, exc_info=True)
            return []
