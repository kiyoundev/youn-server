# #10.4: Schema & API Contract

No backend or proxy changes — this issue is frontend-only, consuming
already-built and already-tested routes.

## API Routes (existing, unchanged)

### `GET /api/stocks`
- **Handler:** `backend/app/api/stocks.py:31`
- **Response:** `StockAlertResponse[]` — every alert, active and paused alike
- Consumed via `/api/proxy/stocks` (generic catch-all proxy, no change)
- Used by both `/portfolio` (all rows) and `/market/[ticker]` (client-side
  filtered to `alert.ticker === ticker`) — **same SWR key both places**, so
  `mutate("/api/proxy/stocks")` after any mutation refreshes both.

### `POST /api/stocks`
- **Handler:** `backend/app/api/stocks.py:71`
- **Request:** `{ ticker, target_price, direction, run_analysis? }` — `alert_type`
  omitted, server defaults to `"buy_signal"` (never exposed in this UI)
- **Error cases:** `400` invalid ticker (Finnhub validation failed) → toast;
  `409` an alert already exists for this ticker+direction+buy_signal → toast
  (see `challenges.md` — the two-section dialog design should make this rare
  but not impossible under a race)

### `PATCH /api/stocks/{alert_id}`
- **Handler:** `backend/app/api/stocks.py:130`
- **Request:** partial — only `target_price`, `active`, `run_analysis` are
  ever sent by this UI (see "Footgun" below for why the payload type must
  not carry more than that)
- **Error cases:** `404`, `409` (collision with another alert on update),
  `422` (direction/alert_type mismatch — unreachable from this UI since
  `alert_type` is never sent and `direction` is fixed per dialog section)

### `DELETE /api/stocks/{alert_id}`
- **Handler:** `backend/app/api/stocks.py:226`
- 204 No Content, unsubscribes from Finnhub feed server-side automatically

### Out of scope, deliberately unused by this issue
- `POST /api/stocks/{alert_id}/analyze` — manual TradingAgents trigger,
  deferred to `#11`
- `GET /api/stocks/{alert_id}/analysis` — deferred to `#11`

## TypeScript Interfaces

New file: `frontend/src/lib/api/stocks.ts`, mirroring `lib/api/items.ts`'s
shape (`request<T>()` helper, `ApiError` class, one function per mutation).

```typescript
// Matches backend/app/schemas/stock_alert.py's StockAlertResponse.
// TradingAgents config fields (deep_think_llm, quick_think_llm,
// anthropic_effort, max_debate_rounds, max_risk_discuss_rounds, analysts)
// and alert_type are intentionally omitted from this UI-facing type — never
// read or written here, out of scope per context.md.
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
// anything wider — backend's update_stock_alert() (stocks.py:172-187) reads
// TradingAgents fields via `model_fields_set`, so an explicit `null` on any
// of them CLEARS a user's saved config. This UI must never construct a
// payload that could carry one of those keys, even accidentally set to
// undefined-that-serializes-wrong. Keeping the type this narrow is the
// actual guardrail — there's no field here to misuse.
export interface StockAlertUpdatePayload {
  target_price?: number;
  active?: boolean;
  run_analysis?: boolean;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

// listStockAlerts() is NOT exported — both pages read the list via useSWR
// on the shared key directly (same pattern watchlist/page.tsx uses for
// Product[]), not through this client, so there's exactly one fetcher.
export function createStockAlert(payload: StockAlertCreatePayload): Promise<StockAlert>;
export function updateStockAlert(alertId: number, payload: StockAlertUpdatePayload): Promise<StockAlert>;
export function deleteStockAlert(alertId: number): Promise<void>;
```

## Contract: one alert per (ticker, direction)

Backend's unique constraint is `(ticker, direction, alert_type)`
(`backend/app/models/stock_alert.py:11-14`). Since this UI never exposes
`alert_type` (always server-default `"buy_signal"`), the effective contract
as seen from the frontend is **at most one alert per (ticker, direction)** —
confirmed with the user as the intended shape, not a simplification of a
richer backend reality: exactly two possible alerts per ticker, "above" and
"below", each independently created/edited/paused/deleted. The two-section
dialog (`challenges.md`) models this directly rather than picking one alert
out of an unbounded list.
