# #23: Schema & API Contract

## API Routes

### `GET /api/market/{ticker}/history`
- **Handler:** `app/api/market.py` (new router, registered with `dependencies=[Depends(verify_api_key)]` same as every other non-health route)
- **Request:**
  - Path: `ticker` (raw ledger/display symbol, e.g. `"AVGO"`, `"RY"` — not pre-suffixed)
  - Query: `range: Literal["1D","1W","1M","3M","6M","YTD","ALL"]` (required); `native_currency: Literal["USD","CAD"] | None` (optional — omitted/`USD` queries the bare ticker, `CAD` applies the same `.TO` rule `prices.yfinance_symbol()` already uses for live quotes)
- **Response:** `list[MarketHistoryPoint]` — `{date: str, close: float}`. `date` is a plain `YYYY-MM-DD` for daily+ ranges (`1M/3M/6M/YTD/ALL`), a full ISO datetime for intraday ranges (`1D/1W`) — `MarketDetailChart`'s `formatHoverLabel` already branches on whether the string contains `"T"`, so this needs no new frontend logic.
- **Error cases:** never raises for an upstream failure — mirrors `get_price_history`'s existing contract (`[]` on failure, logged). An invalid `range`/`native_currency` value is a FastAPI 422 (enum-typed query params).

### `GET /api/portfolio/history`
- **Handler:** `app/api/positions.py` (alongside the existing `/api/portfolio/summary`)
- **Request:** Query: `range: Literal["1D","1W","1M","3M","6M","YTD","ALL"]` (required)
- **Response:** `list[PortfolioHistoryPoint]` — `{date: str, value: float}`, CAD. Same date-format rule as above (intraday ISO-datetime for `1D`, plain date otherwise). An empty ledger (no activities yet) is `[]`.
- **Error cases:** never raises — a per-symbol price/FX fetch failure degrades that symbol's contribution (carries its last known value, or is logged and excluded if it never had one) rather than failing the whole response.

## TypeScript Interfaces

```typescript
// frontend/src/lib/api/market.ts (new) — canonical range vocabulary,
// replacing both mock-market.ts's 8-value DateRange and /portfolio's
// locally-duplicated 7-value one.
export type DateRange = "1D" | "1W" | "1M" | "3M" | "6M" | "YTD" | "ALL";
export const DATE_RANGES: DateRange[] = ["1D", "1W", "1M", "3M", "6M", "YTD", "ALL"];

export interface MarketHistoryPoint {
  date: string; // ISO datetime for 1D/1W, plain YYYY-MM-DD otherwise
  close: number;
}

// frontend/src/lib/api/positions.ts (addition)
export interface PortfolioHistoryPoint {
  date: string; // same date-format rule as MarketHistoryPoint
  value: number; // CAD
}
```

## External API Contracts

- **yfinance** (`get_price_history`, extended) — one `yf.Ticker(symbol).history(period=P, interval=I)` call per `(ticker, range)`, where `(P, I)` comes from a fixed lookup table (no custom `start`/`end` arithmetic — every one of the 7 ranges maps to a native yfinance period string):

  | Range | Interval | yfinance `period` |
  |---|---|---|
  | `1D`  | `5m`  | `"1d"` |
  | `1W`  | `1h`  | `"5d"` |
  | `1M`  | `1d`  | `"1mo"` |
  | `3M`  | `1d`  | `"3mo"` |
  | `6M`  | `1d`  | `"6mo"` |
  | `YTD` | `1d`  | `"ytd"` |
  | `ALL` | `1mo` | `"max"` |

- **Frankfurter** (`get_rate_history`, #74, unchanged) — one range call per currency actually needed (in practice just `"USD"`), reused as-is by `portfolio_history.py`.
