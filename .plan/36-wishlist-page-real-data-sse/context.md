# #36: Context

## Issue Description

Merges former `#10.1` (Wishlist Page, Read-Only) and `#10.3` (Price History Chart) — surfaced while planning the real-data wiring for `frontend/src/app/watchlist/page.tsx`. Two decisions pulled the scope together: (1) price history has no bulk endpoint, so wiring the table sparkline and sheet chart to real data needed its own fetch design regardless of how the original two issues were split; (2) this page adopts Server-Sent Events instead of short-polling — a deliberate learning build, not because polling was insufficient for this app's actual 6-hour scrape cadence (it would have been fine). Full acceptance criteria: `_index.md`.

## Component / Route Summary

### Current State

- `frontend/src/app/watchlist/page.tsx` has the full visual shell (table, sheet side-panel, search, stat summary) built against a hardcoded mock `products` array (lines 41-169), camelCase fields, string IDs, no SWR, every mutation a `console.log` stub.
- `PriceSparkline` (`components/ui/price-sparkline.tsx`) and `ProductPriceChart` (`components/ui/product-price-chart.tsx`) already accept the correct shapes (single-series min-per-date, and per-retailer multi-line respectively) — no component changes needed, only their data source changes.
- Backend already fully built and working: `GET /api/items` (`backend/app/api/items.py:117-127`), `GET /api/items/{pid}/listings/{lid}/history?days=30` (per-listing only, no bulk endpoint), both gated by `verify_api_key` (`main.py:80`).
- `frontend/src/app/api/proxy/[...path]/route.ts` is a generic, GET-only, one-shot `fetch` → `await res.json()` proxy — works for any existing backend route already, no changes needed for the plain-REST half of this issue.
- Backend's price-scraper (`backend/app/scheduler/jobs.py`, `_process_item`, `interval hours=6`) writes `PriceHistory` + updates `watch_items` on every successful scrape, unconditionally. A `PRICE_DROP` `Event` is written **only** on the narrow alert-crossing branch (`jobs.py:117-132`) — most scrapes never touch the `events` table or the existing `asyncio.Queue`/dispatcher system at all.
- No SSE, no streaming route, anywhere in this repo today.

### Target State

- `watchlist/page.tsx` fetches real data via `useSWR("/api/proxy/items", fetcher)`, snake_case types matching the real schemas, `number` IDs threaded through `openId`/keys/handlers.
- Per-listing price history fetched via a `useListingHistory(listingId)` hook; table sparkline and sheet chart both consume it, merged/bucketed by **local calendar day** (client-side, via `Date`'s local-aware methods — no backend timezone changes).
- Backend gains a new, **unconditional** broadcast inside `_process_item`, fired on every successful scrape — a sibling to the existing conditional `Event`/queue write, not a consumer of it (that queue only ever carries alert-worthy IDs and would never see most scrapes).
- New backend route (`GET /api/events/stream`), lightweight in-memory fan-out (not DB-backed — a missed push just means the next reconnect re-syncs via a normal fetch).
- New streaming-capable Next.js proxy handler (separate concern from the existing GET-forward one — relays chunks, never buffers a complete response).
- Frontend `EventSource`, manually managed (not relying on native fixed-interval auto-reconnect) — exponential backoff matching `FinnhubClient._listen()`'s existing pattern, `onopen` triggers a safety-net `mutate("/api/proxy/items")` refetch, two-state connection UX (offline / live-updates-unavailable).
- **No `refreshInterval` polling anywhere on this page** — SSE is the sole live-update trigger.

## Impact & Risk

### Files Changed
- **`frontend/src/app/watchlist/page.tsx`** — delete mock `products` array, wire to real SWR data, rename types to snake_case, delete `stalestCheckedAt()`, null-guard `bestPrice()`/`formatLastChecked()`, `number` IDs throughout, add `EventSource` lifecycle (open/close/backoff/`onopen` safety net) and connection-status UI state.
- **`frontend/src/app/api/proxy/events/stream/route.ts`** (new) — streaming-capable proxy handler, distinct from the existing catch-all's one-shot behavior.
- **`backend/app/scheduler/jobs.py`** (`_process_item`) — add the unconditional broadcast call after the existing `PriceHistory` insert, alongside (not replacing) the existing conditional `Event` write.
- **`backend/app/api/events.py`** (new) — `GET /api/events/stream` route, in-memory fan-out (connection registration/deregistration).
- **`frontend/src/lib/hooks/use-listing-history.ts`** (new, name indicative) — per-listing history fetch hook, shared by table and sheet.
- **`frontend/src/lib/sse-leader.ts`** (new) — `navigator.locks`-based leader election + `BroadcastChannel` relay, so only the leader tab holds a real `EventSource`; mitigates the browser's per-origin HTTP/1.1 connection cap across multiple open tabs. See `challenges.md` #7.

### Dependencies
- **`backend/app/core/auth.py`'s `verify_api_key`** — the new `/api/events/stream` route is gated by it exactly like every other route (mounted via `dependencies=[Depends(verify_api_key)]`, same pattern as `main.py:80-84`).
- **`backend/app/services/stocks.py`'s `FinnhubClient._listen()`** — the manual exponential-backoff pattern for this issue's `EventSource` reconnect logic is a direct copy of this existing precedent, not a new pattern.
- **`frontend/src/app/api/proxy/[...path]/route.ts`** — the existing catch-all proxy is unaffected; the new streaming route is additive, separate from it (per the "separate endpoints" decision — `#37`'s future stock-tick stream won't share this one either).

### New Dependencies
None — `EventSource`, `BroadcastChannel`, and the Web Locks API (`navigator.locks`) are all native browser APIs; FastAPI's `StreamingResponse` is stdlib-adjacent (already part of the `fastapi` dependency already in `requirements.txt`). No new npm or pip packages required.

### Breaking Changes
None — purely additive. Existing `Event`/`asyncio.Queue`/`NotifyConsumer` alert path (Pushover/email) is explicitly untouched by this issue; existing REST proxy route is untouched; `#10.2` (mutations) still lands as `console.log` stubs, unaffected.
