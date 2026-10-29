// Portfolio holdings (issue #19). Mirrors backend/app/schemas/positions.py,
// snake_case on both sides. Reached through the catch-all proxy
// (api/proxy/[...path]/route.ts), which adds the X-API-Key server-side.
import { request } from "@/lib/api/api-client";

export type NativeCurrency = "USD" | "CAD";
export type AssetType = "Stock" | "ETF" | "CDR";

export type PriceStatus =
  | "ok" // fresh quote
  | "stale" // upstream failed; the last known price is served
  | "unavailable" // no price, and none was ever cached
  | "currency_mismatch"; // source reported another currency; price withheld

// One merged holding (same symbol across accounts, per native currency).
// Money is in the holding's native currency and unrounded. Price-derived
// fields are null when status is "unavailable" or "currency_mismatch".
export interface Position {
  symbol: string; // e.g. "AVGO"
  asset_type: AssetType | null;
  last_traded_at: string; // ISO — latest trade across accounts
  native_currency: NativeCurrency;
  shares: number;
  avg_cost: number;
  invested: number; // shares × avg_cost
  current_price: number | null;
  price_status: PriceStatus;
  price_as_of: string | null; // ISO — when the price was fetched upstream
  market_value: number | null; // shares × current_price
  unrealized_gain: number | null; // market_value − invested
  unrealized_gain_pct: number | null; // a fraction: 0.0909 is 9.09%
  allocation: number | null; // a fraction of the priced holdings' CAD value; null = unpriced or no USD rate
}

// One currency's totals. market_value, unrealized_gain and the pct cover
// priced holdings only; invested covers every holding.
export interface CurrencySubtotal {
  currency: NativeCurrency;
  invested: number;
  market_value: number;
  unrealized_gain: number;
  unrealized_gain_pct: number | null; // a fraction, against priced cost only
  holdings_count: number;
  unpriced_count: number; // holdings left out of market_value and gain
}

export interface PortfolioSummary {
  subtotals: CurrencySubtotal[]; // USD first, only currencies with holdings
  cash_cad: number;
  // CAD market value + USD market value × today's USD rate + cash. Null when
  // USD holdings exist but no USD rate does.
  balance_cad: number | null;
  fx_available: boolean;
  fx_stale: boolean; // the rate used is over 24h old
  unpriced_count: number; // across currencies; the balance is a lower bound when > 0
  invested_cad: number; // what the held shares cost in CAD at purchase-time rates, priced or not
}

// Exported so other modules (e.g. the CSV import in nav.tsx) can mutate()
// the exact same SWR keys the portfolio page reads.
export const POSITIONS_KEY = "/api/proxy/positions";
export const PORTFOLIO_SUMMARY_KEY = "/api/proxy/portfolio/summary";

export const getPositions = () => request<Position[]>(POSITIONS_KEY);
export const getPortfolioSummary = () => request<PortfolioSummary>(PORTFOLIO_SUMMARY_KEY);
