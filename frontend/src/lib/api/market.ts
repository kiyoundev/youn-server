// Per-ticker price history (issue #23). Mirrors backend/app/schemas/market.py,
// snake_case on the wire. Reached through the catch-all proxy
// (api/proxy/[...path]/route.ts), which adds the X-API-Key server-side.
import { request } from "@/lib/api/api-client";

// Canonical range vocabulary — the single source of truth for both
// /market/[ticker] and /portfolio's charts. Replaces mock-market.ts's old
// 8-value DateRange (1Y/10Y, no ALL) and /portfolio's own local 7-value one.
export type DateRange = "1D" | "1W" | "1M" | "3M" | "6M" | "YTD" | "ALL";
export const DATE_RANGES: DateRange[] = ["1D", "1W", "1M", "3M", "6M", "YTD", "ALL"];

export type NativeCurrency = "USD" | "CAD";

// date is an ISO datetime for 1D/1W (intraday), a plain YYYY-MM-DD otherwise.
export interface MarketHistoryPoint {
  date: string;
  close: number;
}

export function getMarketHistory(ticker: string, range: DateRange, nativeCurrency?: NativeCurrency) {
  const params = new URLSearchParams({ range });
  if (nativeCurrency) params.set("native_currency", nativeCurrency);
  return request<MarketHistoryPoint[]>(`/api/proxy/market/${encodeURIComponent(ticker)}/history?${params}`);
}
