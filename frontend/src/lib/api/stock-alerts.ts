// Thin data layer between the alarm Sheet's mutation handlers (on
// /market/[ticker]) and fetch() — built on lib/api/api-client.ts's
// request()/ApiError, pointed at /api/proxy/stockalerts instead.
//
// Always goes through /api/proxy/stockalerts — never the backend directly — same
// reason the proxy exists at all: the backend's X-API-Key must never reach
// the browser.
import { request } from "@/lib/api/api-client";

// Matches backend/app/schemas/stock_alert.py's StockAlertResponse.
// TradingAgents config fields (deep_think_llm, quick_think_llm,
// anthropic_effort, max_debate_rounds, max_risk_discuss_rounds, analysts)
// and alert_type are intentionally omitted from this UI-facing type — never
// read or written here (schema.md: out of scope for this issue).
export type AlertDirection = "above" | "below";

export interface StockAlert {
  id: number;
  ticker: string;
  target_price: number;
  direction: AlertDirection;
  last_price: number | null;
  alerted_at: string | null;
  active: boolean;
  run_analysis: boolean;
  created_at: string;
}

export interface StockAlertCreatePayload {
  ticker: string;
  target_price: number;
  direction: AlertDirection;
  run_analysis?: boolean;
}

// Deliberately optional-only, deliberately NOT a Partial<StockAlert> or
// anything wider — backend's update_stock_alert() (stock_alerts.py:172-187) reads
// TradingAgents fields via `model_fields_set`, so an explicit `null` on any
// of them CLEARS a user's saved config. This type has no field to misuse in
// the first place — that's the actual guardrail, not a runtime check.
export interface StockAlertUpdatePayload {
  target_price?: number;
  active?: boolean;
  run_analysis?: boolean;
}

const BASE = "/api/proxy/stockalerts";

// listStockAlerts() is deliberately not exported here — both /portfolio and
// /market/[ticker] read the list via useSWR("/api/proxy/stockalerts", ...)
// directly (same pattern watchlist/page.tsx uses for Product[]), so there's
// exactly one fetcher and one shared cache entry between the two pages.

export function createStockAlert(payload: StockAlertCreatePayload): Promise<StockAlert> {
  return request<StockAlert>(BASE, { method: "POST", body: JSON.stringify(payload) });
}

export function updateStockAlert(alertId: number, payload: StockAlertUpdatePayload): Promise<StockAlert> {
  return request<StockAlert>(`${BASE}/${alertId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteStockAlert(alertId: number): Promise<void> {
  return request<void>(`${BASE}/${alertId}`, { method: "DELETE" });
}
