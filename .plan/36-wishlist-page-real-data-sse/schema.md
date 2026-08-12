# #36: Schema & API Contract

## API Routes

### `GET /api/items` (existing — no change)
- **Handler:** `backend/app/api/items.py:117-127`
- **Request:** none
- **Response:** `list[ProductResponse]`
- **Error cases:** `401` if `X-API-Key` missing/wrong (`verify_api_key`)

### `GET /api/items/{product_id}/listings/{listing_id}/history` (existing — no change)
- **Handler:** `backend/app/api/items.py:291-310`
- **Request:** query param `days` (default 30, range 1-365)
- **Response:** `list[PriceHistoryResponse]`
- **Error cases:** `401` (auth), `404` if listing/product not found

### `GET /api/events/stream` (new)
- **Handler:** `backend/app/api/events.py` (new file)
- **Request:** none — a long-lived `GET`, connection kept open
- **Response:** `text/event-stream`, chunked, unbounded duration. Each event: `data: {"product_id": <int>, "listing_id": <int>}\n\n` — deliberately minimal, no full payload (frontend refetches on receipt rather than trusting the pushed data as authoritative)
- **Error cases:** `401` if `X-API-Key` missing/wrong (same `verify_api_key` dependency as every other route)
- **Design notes:** in-memory fan-out only (a `set` of open connections), not DB-backed. No `id:` field, no `Last-Event-ID` replay support — a missed push is corrected by the frontend's `onopen` safety-net refetch, not by server-side buffering. Dedicated to this feature; `#37`'s future stock-tick broadcast gets its own separate endpoint, not multiplexed onto this one.

### `GET /api/proxy/items` (existing catch-all — no change)
- **Handler:** `frontend/src/app/api/proxy/[...path]/route.ts`
- Unaffected by this issue — the wishlist page's `useSWR("/api/proxy/items", fetcher)` call is new, but the proxy handler itself needs no changes to serve it.

### `GET /api/proxy/events/stream` (new)
- **Handler:** `frontend/src/app/api/proxy/events/stream/route.ts` (new file — separate from the existing catch-all, since streaming needs a fundamentally different handler shape)
- **Request:** none (browser's `EventSource`, no custom headers possible — not needed, since `X-API-Key` is attached on the proxy's own outbound leg to the backend, same as every other route)
- **Response:** relays the backend's `text/event-stream` chunk-by-chunk — must not buffer, must not `await` a "complete" response the way the existing catch-all does (`await resp.text()`)
- **Error cases:** propagates backend's `401`/connection failure; browser's `EventSource` handles retry via the manual reconnect logic (Implementation step 3)

## TypeScript Interfaces

```typescript
// Replaces the mock camelCase interfaces in watchlist/page.tsx (lines 23-39)
interface Listing {
  id: number;                                              // was string
  retailer: string;
  url: string;
  last_price: number | null;                               // was `price: number`, always present
  last_scrape_status: "ok" | "oos" | "error" | null;       // new — not in mock
  active: boolean;                                          // new
  last_checked: string | null;                              // was `lastCheckedAt`, always present
  product_id: number;
  created_at: string;
}

interface Product {
  id: number;                                               // was string
  name: string;
  target_price: number;                                     // was targetPrice
  alerted_at: string | null;                                // new
  status: "watching" | "triggered" | "paused" | "failed";  // server-computed
  last_checked: string | null;                              // server-computed
  listings: Listing[];
  created_at: string;
}

// New — matches backend/app/schemas/price_history.py
interface PriceHistoryPoint {
  id: number;
  watch_item_id: number;   // NOT listing_id — matches backend field name exactly
  price: number;
  checked_at: string;
}

// New — SSE broadcast payload
interface ListingChangedEvent {
  product_id: number;
  listing_id: number;
}
```

## External API Contracts
None — this issue is entirely internal (frontend ↔ this app's own backend). No third-party API involved.
