# #19: Context

## Issue Description
Portfolio insights page — holdings, invested amount, current value, unrealized P&L, cash and account balance — computed from the Wealthsimple activity ledger (#33), not entered by hand. No `Position` table or CRUD; the user re-uploads an activities export after trading.

**Backend**
- New `app/api/positions.py`: `GET /api/positions` (holdings from `compute_positions()` + `current_price` in native currency) and `GET /api/portfolio/summary` (per-currency USD/CAD subtotals of invested, market value, unrealized gain and %, cash, account balance in CAD via `fx_rates`). Registered in `main.py` behind `verify_api_key`.
- Price sources: USD-native → Finnhub REST; CAD-native → yfinance (`.TO` appended if missing, config override map). Cross-check yfinance's reported currency against inferred native currency; mismatch → no price + flag.
- One shared TTL cache (~15s); last-known price on rate-limit / upstream error. Never `subscribe()` for holdings.
- Ledger cache (added 2026-10-15): merged holdings + cash held in memory, cleared by the import and reset routes, so a 30s poll costs no DB read. Reference diagrams: `.doc/diagrams/portfolio-pricing-flow.html`, and the cache's lifecycle (load, hit, invalidate) in `.doc/diagrams/ledger-cache-lifecycle-sequence.html`; the page's two requests end to end in `.doc/diagrams/portfolio-page-flow-sequence.html`.

**Frontend** — `/portfolio`: real holdings rows (logo from Wealthsimple's host with a ticker-box fallback, ticker, asset type badge (Stock / ETF / CDR, hidden when unknown), shares, "Last traded Mon YYYY", market value, unrealized gain $ and % colour-coded, status tooltips), the summary trio (Companies / Balance = cash / Committed = `invested_cad`), the real `balance_cad` as the big total, loading / error / empty states, 30s SWR poll, no SSE, no realized gain. Allocation column postponed.

## Component / Route Summary

### Current State
- `backend/app/services/positions.py` — `compute_positions(activities) -> (holdings, cash, warnings)`; `Holding(account_id, symbol, shares, native_currency, avg_cost_native, avg_cost_cad)`. Only `api/activities.py` calls it (import integrity gate). Its docstring already anticipates #19's read endpoints.
- `Activity` model (`models/activity.py`) satisfies `ActivityLike`, so DB rows can be passed straight in.
- `FinnhubClient.get_price()` (`services/stocks.py`) — REST `/quote`, no cache, returns `None` on any error. `app.state.finnhub` holds the instance. `get_price_history` already uses yfinance through `run_in_executor` (pattern to copy).
- `fx_rates` table + `GET /api/fx-rates` — `rates: {"USD": 1.38}` (CAD implicit 1.0), `stale` flag.
- Cash is always CAD: the CSV parser rejects every non-CAD activity currency.
- `frontend/src/app/portfolio/page.tsx` (436 lines) — Holdings tile maps `holdingsData` (mock-portfolio.ts); overview trio ("Companies" / "$8,000" / "$5,000") hardcoded; chart, donut and growth rate are mock; Watchlist tile and Popular Assets carousel are mock.
- SWR polling convention: `POLL_INTERVAL_MS = 30_000` (`lib/polling.ts`); API calls go through the generic `/api/proxy/[...path]` catch-all, so new backend routes need no new proxy code.

### Target State
- New `services/prices.py` (`PriceService`): routing by native currency, TTL cache, stale fallback, currency check, yfinance in executor.
- New `api/positions.py` with the two read routes; `schemas/positions.py` for response models.
- Positions merged across accounts per `(symbol, native_currency)`.
- `/portfolio` Holdings tile and summary figures use real data; mock `Position` type and `holdingsData` removed. Empty ledger shows an empty state linking to the import upload.

## Impact & Risk

### Files Changed
- **`backend/app/services/prices.py`** (new) — price routing, cache, yfinance + Finnhub adapters
- **`backend/app/api/positions.py`** (new) — `GET /api/positions`, `GET /api/portfolio/summary`
- **`backend/app/schemas/positions.py`** (new) — response models
- **`backend/app/services/asset_types.py`** (new, 2026-10-28) — `AssetTypeService`: Stock / ETF / CDR / `null` per holding, from yfinance, cached per process; separate from `PriceService`
- **`backend/app/main.py`** — register router with `verify_api_key`; create `PriceService` and the ledger cache in lifespan on `app.state`
- **`backend/app/api/activities.py`** — import (line ~110) and reset (line ~166) routes call `invalidate()` on the ledger cache after commit
- **`backend/tests/...`** (new) — price service, merge logic, summary maths, route tests
- **`frontend/src/lib/api/positions.ts`** (new) — types + fetchers
- **`frontend/src/components/ui/ticker-logo.tsx`** (new) — logo with exchange fallback chain and ticker-box placeholder
- **`frontend/src/components/nav.tsx`** — refreshes the portfolio SWR keys after an import; search no longer hides held tickers
- **`frontend/src/app/portfolio/page.tsx`** — Holdings tile + summary figures on real data, empty state
- **`frontend/src/lib/mock-portfolio.ts`** — drop `Position` / `holdingsData`; keep watchlist + ticker directory mocks
- **`.doc/issues.md`** — tick #19 criteria; add the missing-issue note (below)

### Dependencies
- **`compute_positions()`** — reused (since 2026-10-28 it also records `last_traded_at` per holding); it raises `LedgerImportError` on a bad ledger, which should not occur for a ledger that passed import, but the routes must still map it to a 500 with a clear message rather than crash.
- **`FinnhubClient.get_price()`** — reused as-is (REST only).
- **`fx_rates`** — read directly via `FxRate`; stale/missing handled in the summary.
- **`yfinance>=0.2,<0.3`** — already in `requirements.txt`; no new packages.

### Gap now recorded
Issue #69 in `.doc/issues.md` covers real quote / stats for `/market/[ticker]` (still `getMarketDetail()` mock). The portfolio chart, donut and growth rate remain mock until #23.
