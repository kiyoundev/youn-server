// Thin data layer between the alarm Sheet's mutation handlers (on
// /market/[ticker]) and fetch() — same shape as lib/api/items.ts's
// request()/ApiError pattern, pointed at /api/proxy/stockalerts instead.
//
// Always goes through /api/proxy/stockalerts — never the backend directly — same
// reason the proxy exists at all: the backend's X-API-Key must never reach
// the browser.

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

// Thrown on any non-2xx response so callers can branch on status (e.g. 409
// -> "alert already exists" toast vs. a generic failure toast) instead of
// every call site re-parsing the response body by hand.
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

const BASE = "/api/proxy/stockalerts";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Request failed with status ${res.status}`);
  }

  // DELETE returns 204 with no body — nothing to parse.
  if (res.status === 204) return undefined as T;
  return res.json();
}

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
