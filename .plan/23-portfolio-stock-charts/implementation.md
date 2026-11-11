# #23: Implementation

## Steps

### 1. Backend — per-ticker history (`get_price_history` + new route)
- [x] `app/services/stocks.py`: change `get_price_history(ticker, period="1mo")` → `get_price_history(ticker, range_, native_currency=None)`. Add a module-level `_RANGE_TO_YFINANCE: dict[str, tuple[str, str]]` (period, interval) per the table in `schema.md`. When `native_currency == "CAD"`, resolve the query symbol through `prices.yfinance_symbol()` (import from `app.services.prices`) before calling `yf.Ticker(...)`; otherwise use the bare ticker. `date` in each returned point is `str(idx)` for intraday bars (keeps the time component) vs. `str(idx.date())` for daily+ — branch on whether the resolved interval is intraday (`5m`/`1h`) vs not.
- [x] `app/schemas/market.py` (new): `MarketHistoryPoint` (`date: str`, `close: float`).
- [x] `app/api/market.py` (new): `GET /api/market/{ticker}/history`, `range`/`native_currency` as typed `Literal` query params, calls `get_price_history` via the existing `FinnhubClient` instance (`request.app.state.finnhub`, mirroring `get_price_service`'s pattern in `app/api/positions.py`), maps the result to `list[MarketHistoryPoint]`.
- [x] `app/main.py`: `app.include_router(market.router, dependencies=[Depends(verify_api_key)])`.
- [x] Update `tests/test_stocks.py`'s 2 existing `get_price_history` tests for the new signature (`range_` instead of `period`).

### 2. Backend — portfolio value history (new service + route)
- [x] `app/services/portfolio_history.py` (new):
  1. Load the full `Activity` list once (`select(Activity)`, same query `LedgerCache._load` already runs — this function does **not** go through `LedgerCache`, since that cache only remembers today's collapsed result, not the day-by-day trail).
  2. Compute the date points for the requested range: daily-granularity ranges (`1W/1M/3M/6M/YTD/ALL`) get one point per calendar day from `range_start` to today (`ALL`'s `range_start` is the earliest activity's date, not an arbitrary window); `1D` is intraday (reuses the per-symbol intraday series' own timestamps as the canonical x-axis — see step 3 below, no separate date-point list needed for it).
  3. For each daily-granularity date point `D`: `compute_positions([a for a in activities if a.effective_at.date() <= D])` → that day's holdings+cash. For `1D`: a single `compute_positions(activities)` call (today = the full ledger already) — per the grill-me decision, today's intraday points all use this one constant share count; only price moves intraday.
  4. Collect the union of every `(symbol, native_currency)` pair that appears in any of those holdings across the whole range.
  5. For each distinct pair, one `get_price_history(symbol, range_, native_currency)` call (concurrent via `asyncio.gather`, mirroring `PriceService.get_prices`' existing concurrency pattern) — one call per symbol for the *entire* range, not per date point.
  6. One `get_rate_history(session, "USD", range_start, today)` call (#74, unchanged) if any held symbol is USD-native; CAD-native symbols need no FX.
  7. Merge: for each date point, `value = cash + sum(shares * price_in_cad)` over that point's holdings, where each symbol's price is read from its own pre-fetched series with carry-forward (same "last known, never zero" rule `get_rate_history` already established) and USD prices are converted using that date's FX rate from `get_rate_history`'s result. A symbol with literally no price data anywhere in its series (not just a gap — a total fetch failure) is logged and excluded from that point's sum rather than counted as 0 silently; see `challenges.md`.
- [x] `app/schemas/positions.py`: add `PortfolioHistoryPoint` (`date: str`, `value: float`, `total_deposits_cad: float` — a later addition past the original design, see below).
- [x] `app/api/positions.py`: `GET /api/portfolio/history?range=1W`, calls `portfolio_history.get_portfolio_history(db, range_)`.

### 3. Backend — testing
- [x] `tests/services/test_stocks.py` (or extend existing `test_stocks.py`): range→(period,interval) mapping for all 7 ranges; `.TO` suffix applied only when `native_currency="CAD"`; date format (datetime string vs plain date) matches the intraday/daily split.
- [x] `tests/services/test_portfolio_history.py` (new): date-point generation per range (incl. `ALL` anchored to the earliest activity); a stock bought mid-range contributes nothing before its first buy (reuses `compute_positions`' own tested buy/sell math, no need to re-prove it here — just prove the prefix-filtering wiring); carry-forward for a missing close; a symbol with a total fetch failure excluded, not zeroed; USD conversion via `get_rate_history`; `1D`'s shares-constant behavior.
- [x] `tests/api/test_market_routes.py` (new) and an addition to `tests/api/test_positions_routes.py`: both new routes' happy path, an invalid `range`/`native_currency` 422s.

### 4. Frontend — range-type consolidation
- [x] `frontend/src/lib/api/market.ts` (new): canonical `DateRange`/`DATE_RANGES` (7 values), `MarketHistoryPoint`, `getMarketHistory(ticker, range, nativeCurrency?)` (mirrors `lib/api/positions.ts`'s `request<T>()` pattern, proxied through `/api/proxy/market/...`).
- [x] `frontend/src/lib/mock-market.ts`: remove `DateRange`/`DATE_RANGES`/`generateMockPriceSeries` (now superseded). Everything else (`mockMarketDetails`, `Activity`, `activityTypeLabel`, `getMarketDetail`, `getActivitiesForTicker`, `getPositionForTicker`, `getTotalPortfolioValue`) stays — unrelated to this issue, still mock.
- [x] `frontend/src/lib/api/positions.ts`: add `PortfolioHistoryPoint`, `getPortfolioHistory(range)`.

### 5. Frontend — wiring
- [x] `frontend/src/app/market/[ticker]/page.tsx`: import `DateRange`/`DATE_RANGES` from `lib/api/market.ts` instead of `lib/mock-market.ts`; replace `generateMockPriceSeries(ticker, detail.currentPrice, selectedRange)` with `useSWR` keyed on `[ticker, selectedRange]` calling `getMarketHistory` (pass `native_currency` from the position lookup when this ticker is held, per `schema.md`'s decision — omitted otherwise). No `refreshInterval`.
- [x] `frontend/src/app/portfolio/page.tsx`: wired to `getPortfolioHistory(selectedRange)` via `useSWR`, no `refreshInterval`. `investedAmount={summary?.invested_cad}` passed into `PortfolioLineChart`. The %-change design changed past this plan's original sketch (`(balance - history[0].value)/history[0].value`): that naive formula conflated deposits with real return. Replaced with a deposit-adjusted formula — `(value[active]-value[0]) - (total_deposits_cad[active]-total_deposits_cad[0])`, % against `total_deposits_cad[active]` — verified against a real Wealthsimple account's own reported returns (exact match on ALL/6M once a live-quote gap in the comparison was backed out). Badge and headline both react to chart hover (defaulting to the selected range's own latest point when unhovered); "Current Value (CAD)" label removed per user request (read as misleading next to the %), badge left at the (now sole) left position, bumped to `text-base` (16px).

### 6. Cleanup
- [x] `ruff` clean (backend), `eslint`/`tsc` clean (frontend) — repo-wide, not just touched files; the only pre-existing findings are unrelated to #23 (StockAlert `== True` in stocks.py, a couple of unused imports/lambdas elsewhere).
- [ ] Tick #23 in `.doc/issues.md` once both halves pass manual verification (user-run, per this project's convention — no dev server/browser automation here).
