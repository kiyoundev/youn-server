# #19: Schema & API Contract

## API Routes
Both routes are read-only, registered behind `verify_api_key`, reached from the browser through the existing `/api/proxy/[...path]` catch-all (`/api/proxy/positions`, `/api/proxy/portfolio/summary`). No Postgres schema change — positions are never stored.

### `GET /api/positions`
- **Handler:** `backend/app/api/positions.py::get_positions`
- **Request:** none
- **Response:** `PositionResponse[]` — a bare list. Empty ledger → `[]` (200, not an error). No ledger warnings here: they are an import-time notice (#33).
- **Logic:** load all `Activity` rows → `compute_positions()` → merge by `(symbol, native_currency)` → `PriceService.get_prices()` and `AssetTypeService.get_types()` (both concurrent) → build rows. Sorted largest first by value in CAD (the allocation; native market value when there is no USD rate), unpriced rows last. The USD rate is read here too (one `fx_rates` lookup), for `allocation`. A type lookup that fails or times out gives `asset_type: null` and never changes a row's price fields.
- **Error cases:** 500 if `compute_positions` raises `LedgerImportError` (ledger corrupted after import — message passed through); per-symbol price failures never fail the route, they become `price_status` values.

### `GET /api/portfolio/summary`
- **Handler:** `backend/app/api/positions.py::get_portfolio_summary`
- **Request:** none
- **Response:** `PortfolioSummary` (below).
- **Logic:** same positions + prices (shared cache means no second upstream fetch) → per-currency subtotals → cash from `compute_positions` → CAD balance = Σ market value converted via `fx_rates` + cash.
- **Error cases:** as above. Missing/absent USD FX row → `balance_cad: null`, `fx_available: false` (page shows "—" and a note) instead of a 500. Stale FX (>24h) → still converted, `fx_stale: true`.

## TypeScript Interfaces
```typescript
// frontend/src/lib/api/positions.ts — mirrors backend/app/schemas/positions.py
export type NativeCurrency = "USD" | "CAD";

export type PriceStatus =
  | "ok"                // fresh quote (≤ TTL)
  | "stale"             // upstream failed; last known price served
  | "unavailable"       // no price and none ever cached (or Finnhub key unset)
  | "currency_mismatch"; // yfinance currency ≠ native currency; price withheld

// Yahoo files CDRs as "ETF", so a CAD-native ETF whose shortName contains
// "CDR" is reported as "CDR". null = unknown type or a failed lookup: no badge.
export type AssetType = "Stock" | "ETF" | "CDR";

export interface Position {
  symbol: string;                 // ledger symbol, e.g. "AVGO"
  native_currency: NativeCurrency;
  shares: number;                 // summed across accounts
  avg_cost: number;               // native currency, share-weighted
  current_price: number | null;   // native currency
  price_status: PriceStatus;
  price_as_of: string | null;     // ISO — when the price was fetched upstream
  market_value: number | null;    // shares × current_price
  invested: number;               // shares × avg_cost
  unrealized_gain: number | null; // market_value − invested
  unrealized_gain_pct: number | null; // a fraction: 0.0909 is 9.09%
  asset_type: AssetType | null;
  last_traded_at: string;         // ISO — latest Trade row across accounts (today: the last purchase)
  allocation: number | null;      // fraction of the priced holdings' CAD value; null = unpriced or no USD rate
}

export interface CurrencySubtotal {
  currency: NativeCurrency;
  invested: number;
  market_value: number;           // priced holdings only
  unrealized_gain: number;        // priced holdings only
  unrealized_gain_pct: number | null;
  holdings_count: number;
  unpriced_count: number;         // holdings excluded from market_value/gain
}

export interface PortfolioSummary {
  subtotals: CurrencySubtotal[];  // only currencies that have holdings
  cash_cad: number;
  balance_cad: number | null;     // Σ market value (→ CAD) + cash; null if FX unavailable
  fx_available: boolean;
  fx_stale: boolean;
  unpriced_count: number;         // total across currencies — balance is a lower bound when > 0
  invested_cad: number;           // CAD paid for the held shares at purchase-time rates, priced or not
}
```

## Backend response models (Pydantic)
`PositionResponse`, `CurrencySubtotal`, `PortfolioSummary` in `backend/app/schemas/positions.py` — field-for-field with the TypeScript above (snake_case on both sides, as with `AccountImportResult`).

## External API Contracts
- **Finnhub REST `GET /api/v1/quote?symbol={SYM}`** (via `FinnhubClient.get_price`) — key field `c` (current price), USD US-listed symbols only. **Verified live:** `AVGO` → 200 `c=344.33`; `AVGO.TO`, `SHOP.TO`, `XIU.TO` → **403 "You don't have access to this resource."** on our free key. Response carries no currency, so no cross-check is possible for USD-native holdings. Limit 60 calls/min per key.
- **yfinance `Ticker(sym).fast_info`** — `last_price`, `currency`, `previous_close`, `exchange`. **Verified live:** `AVGO.TO` → 13.08 CAD / TOR; `AVGO` → 344.33 USD / NMS. Unofficial Yahoo scrape: no key, no SLA; Yahoo's raw chart endpoint returned HTTP 429 without a browser `User-Agent`. Blocking calls → `run_in_executor`.
- **Logo (changed 2026-10-29)** — `https://logos.wealthsimple.com/{ticker}-{exchange}.png` (lowercase; `.TO`-style suffix stripped). Unofficial, no key. **Probed:** `ry-xtse`, `nvda-xnas`, `sofi-xnas`, `etn-xnys`, `googl-xnas`, `avgo-xnas` → 200 PNG; `spy-arcx`, `xiu-xtse`, `avgo-xtse`, an unknown ticker → 403. `.svg` exists only for some tickers, so `.png` is always used. The ledger carries no exchange, so `ticker-logo.tsx` tries `xtse` for CAD and `xnas` then `xnys` for USD; when all fail it renders a white box with the full ticker. Earlier choice: Finnhub's `static2.finnhub.io/.../stock_logo/{ticker}.png`.
