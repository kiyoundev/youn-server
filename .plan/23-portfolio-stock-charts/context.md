# #23: Context

## Issue Description

Two bundled sub-issues under one ticket (`.doc/issues.md`):

**Per-ticker price chart.** `FinnhubClient.get_price_history()` (`app/services/stocks.py`) already exists (#4) but is wired to no route — `period`-only, daily-only bars. The issue originally proposed adding `interval`, a new ticker-scoped route, and a brand-new `StockHistoryChart` component with row-expand UI on `/portfolio` and `1M/1Y/3Y/ALL` presets.

**Portfolio value history (added 2026-10-29).** `/portfolio`'s overview chart (`PortfolioLineChart`, ranges `1D/1W/1M/3M/6M/YTD/ALL`) and the %-change beside the total are still mock (`chartDataByRange` in `page.tsx`). #19 made the big total real; this makes the chart and the per-range change real. Needs, per past date in range: shares held then (ledger-derived, so a stock bought later contributes nothing earlier), that date's close per symbol, that date's USD→CAD rate (via #74), plus cash. A day with no close carries the last known one, never zero.

Acceptance criteria (`.doc/issues.md`, both sub-sections) — restated against the corrected scope below where the original text is superseded:
- `get_price_history()` accepts a range and returns correctly-shaped points for each of `1D/1W/1M/3M/6M/YTD/ALL`
- `GET /api/market/{ticker}/history?range=...` returns those points; a CAD-native ticker resolves through the same `.TO` suffix rule live quotes already use
- `/market/[ticker]`'s existing chart renders real data, switching range re-fetches
- `/portfolio`'s overview chart plots real portfolio value in CAD for all 7 ranges; no mock `chartDataByRange` remains
- The big Current Value total is identical across ranges; the change beside it is `(total − value at range start) / value at range start`
- A past point uses the shares held that date and that date's prices/FX rate; a newly-bought stock adds nothing before its first buy; a missing close carries the last known one
- The dashed invested line uses `summary.invested_cad`

## Component / Route Summary

### Current State

**Backend:**
- `get_price_history(ticker, period="1mo")` (`app/services/stocks.py`) — single yfinance call, daily bars only, `period`-only. Zero callers (confirmed via grep — only its own 2 tests). Free to change its signature.
- `compute_positions(activities)` (`app/services/positions.py`) — pure function, takes any `Sequence[ActivityLike]`, derives holdings+cash from scratch. Used today only on the *full* ledger (via `LedgerCache`), for "what do I own right now." Nothing currently asks it "what did I own on day D" — but since the full ledger already passes `compute_positions`' own integrity checks, any chronological prefix of it (activities up to day D) is itself a valid historical state. No new reconstruction logic needed — just feed it a date-filtered slice.
- `LedgerCache` (`app/services/ledger_cache.py`) only caches *today's* derived snapshot (holdings/cash already collapsed to final numbers) — it has no memory of the day-by-day trail. The permanent source of truth for that trail is the `activities` table itself (#33's design), which the historical route reads directly, the same way `LedgerCache._load` already does (`select(Activity)`).
- `get_rate_history(session, currency, start, end)` (`app/services/fx.py`, #74, already shipped) — exactly the per-date FX lookup this issue needs, with carry-forward and graceful-omission semantics already matching what this issue wants for prices too.
- `PriceService.yfinance_symbol()` (`app/services/prices.py`) — the existing `.TO`-suffix rule for CAD-native holdings' *live* quotes; the historical route needs the same rule, not a second one.

**Frontend — this is the part the original issue text didn't anticipate:**
- `/market/[ticker]/page.tsx` already exists as a full detail page (built after #23 was first written) with a real `MarketDetailChart`, a real `DateRange` type (`1D/1W/1M/3M/6M/YTD/1Y/10Y`, from `lib/mock-market.ts`), and real alert data (`createStockAlert`/`updateStockAlert`/`deleteStockAlert`). Only the price series (`generateMockPriceSeries`) and a cluster of unrelated fields (bid/ask/volume/P-E/dividends/`getMarketDetail`) are mock — those unrelated fields stay mock, out of scope here.
- `/portfolio`'s holdings rows already `<Link href={/market/${symbol}}>` — there is no row-expand interaction anywhere in the current UI. The issue's "new `StockHistoryChart`, row-expand" plan is stale against this.
- `/portfolio/page.tsx` already defines its own local `DateRange`/`DATE_RANGES` (`1D/1W/1M/3M/6M/YTD/ALL`) and `chartDataByRange` (hardcoded mock), feeding the already-wired `PortfolioLineChart` component (which already accepts an `investedAmount` reference-line prop — currently never passed).
- `mock-market.ts`'s `DateRange` (8 values) and `/portfolio/page.tsx`'s local `DateRange` (7 values) are two different, independently-defined range vocabularies for what should be the same concept.

### Target State

- **Range set unified to 7 values** (`1D/1W/1M/3M/6M/YTD/ALL`) across both charts — matches what `/portfolio` already uses; `/market/[ticker]` drops `1Y`/`10Y`, gains `ALL`. Defined once (`lib/api/market.ts`), imported by both pages instead of two separate local definitions.
- `get_price_history(ticker, range_, native_currency=None)` resolves the range to a native yfinance `(period, interval)` pair internally (table below) — no custom `start`/`end` arithmetic needed anywhere, since every one of the 7 ranges maps to an existing yfinance period string.
- New `GET /api/market/{ticker}/history?range=1M&native_currency=CAD` route (`app/api/market.py`) — ticker-scoped, reusable without a `Position`/`StockAlert` existing, matching the issue's original reasoning for not nesting it under `/api/stockalerts/...`.
- New `app/services/portfolio_history.py` — orchestrates: date points for the range → `compute_positions` on a ledger-prefix per point (today's point uses the full ledger, no filtering) → the union of every symbol ever held across those points → one `get_price_history` call per distinct symbol for the whole range (concurrent) → one `get_rate_history` call for USD across the whole range → merge into `[{date, value}]`.
- New `GET /api/portfolio/history?range=1W` route (`app/api/positions.py`, alongside `/api/portfolio/summary`).
- `/market/[ticker]/page.tsx` and `/portfolio/page.tsx` both fetch real data via `useSWR`, keyed by range, **no `refreshInterval`** — a past day's value never changes, so there's nothing to poll; only switching the range (a new SWR key) triggers a refetch.
- `/portfolio/page.tsx` wires `investedAmount={summary?.invested_cad}` into the already-existing prop, and derives the range's %-change from the fetched series' first point vs. `summary.balance_cad`.

## Impact & Risk

### Files Changed
- **`backend/app/services/stocks.py`** — `get_price_history` signature changes from `(ticker, period)` to `(ticker, range_, native_currency=None)`; adds the range→(period,interval) table and the `.TO`-suffix call-through to `prices.yfinance_symbol()`.
- **`backend/app/services/portfolio_history.py`** (new) — the orchestration described above.
- **`backend/app/schemas/market.py`** (new) — `MarketHistoryPoint`.
- **`backend/app/schemas/positions.py`** — add `PortfolioHistoryPoint`.
- **`backend/app/api/market.py`** (new) — `GET /api/market/{ticker}/history`.
- **`backend/app/api/positions.py`** — add `GET /api/portfolio/history`.
- **`backend/app/main.py`** — register the new router.
- **`frontend/src/lib/api/market.ts`** (new) — canonical `DateRange`/`DATE_RANGES`, `MarketHistoryPoint`, `getMarketHistory()`.
- **`frontend/src/lib/api/positions.ts`** — add `PortfolioHistoryPoint`, `getPortfolioHistory()`.
- **`frontend/src/lib/mock-market.ts`** — remove `DateRange`/`DATE_RANGES`/`generateMockPriceSeries` (superseded by the real ones above); `mockMarketDetails`/`Activity`/etc. stay, unrelated to this issue.
- **`frontend/src/app/market/[ticker]/page.tsx`** — real chart data, updated range type import.
- **`frontend/src/app/portfolio/page.tsx`** — real chart data, drop local `DateRange`/`chartDataByRange`, wire `investedAmount`, derive %-change.

### Dependencies
- **`app/services/fx.py`'s `get_rate_history`** (#74) — used as-is, no changes.
- **`app/services/positions.py`'s `compute_positions`** — used as-is (called on a filtered slice), no changes.
- **`app/models/activity.py`'s `Activity`** — read directly (raw rows), bypassing `LedgerCache`.
- **`MarketDetailChart`, `PortfolioLineChart`** (frontend) — used as-is; both already handle ISO-date-vs-datetime formatting and reference lines, no component changes needed.

### Breaking Changes
- `get_price_history`'s signature changes (`period` → `range_`); safe — zero existing callers outside its own tests (confirmed via grep).
- `mock-market.ts`'s `DateRange` shrinks from 8 values to 7 (drops `1Y`/`10Y`, gains `ALL`) — only consumer is `/market/[ticker]/page.tsx`, updated in the same change.
