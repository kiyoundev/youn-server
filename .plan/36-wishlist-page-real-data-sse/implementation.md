# #36: Implementation

## Steps

### 1. Backend — unconditional broadcast + streaming route
- [x] Add an in-memory fan-out (a `set` of open connection handles) in a new module, e.g. `backend/app/services/sse.py` — `register()`, `unregister()`, `broadcast(payload)`
- [x] Wire `register()`/`unregister()` into a new `GET /api/events/stream` route (`backend/app/api/events.py`), returning `StreamingResponse` with `media_type="text/event-stream"`, gated by `verify_api_key` (mount via `dependencies=[Depends(verify_api_key)]`, matching `main.py:80-84`'s existing pattern)
- [x] Detect client disconnect inside the streaming generator and call `unregister()` on drop — required, otherwise the fan-out set leaks a dead entry per closed tab. Built as a **ping/write-and-catch** pattern, not `await request.is_disconnected()`: on each idle timeout (`_PING_INTERVAL`, 15s), `yield ": ping\n\n"` instead of passively asking a status flag. `is_disconnected()` only reflects a disconnect signal the ASGI layer already received (a clean FIN) — a silent death (wifi drop, no clean close) never sends that signal, so it would report "still connected" forever. An active write forces the OS to eventually surface the failure instead of waiting on a signal that may never arrive. Cleanup itself is unchanged — the existing `try/finally` around the loop already handles it (`finally` runs on `GeneratorExit`/`CancelledError` too, both `BaseException`, not `Exception` — no explicit `except` needed). Full reasoning: `challenges.md` #8.
- [x] In `backend/app/scheduler/jobs.py`'s `_process_item`, add the broadcast call — unconditional, every successful scrape, as a sibling to the existing conditional `Event`/queue write, not a replacement or a consumer of it. Placed after all three `commit()` branches converge (not right after the `PriceHistory` insert as originally written here — that insert is uncommitted at that point; see the gap analysis at the top of this session), using `listing.id` (the listing actually scraped), not `winning.id` (the alert `Event`'s cheapest-listing field).
- [x] Register the new router in `main.py`, same `include_router(..., dependencies=[Depends(verify_api_key)])` pattern as `items`/`stocks`/`poll`

### 2. Frontend proxy — streaming handler
- [x] New file `frontend/src/app/api/proxy/events/stream/route.ts` — separate from the existing catch-all (`[...path]/route.ts`), since this needs a fundamentally different shape: open an outbound `fetch` to the backend's `/api/events/stream` with `X-API-Key` attached, then relay the response body chunk-by-chunk into this route's own `Response`, never buffering/`await`-ing completion
- [x] Propagate the incoming request's abort signal to the outbound backend connection, so a browser disconnect closes the backend connection too (not left open/leaking) — via `signal: request.signal` on the outbound `fetch`

### 3. Frontend — real data wiring (replaces mock)
- [x] Delete the hardcoded `products` array (`watchlist/page.tsx:41-169`)
- [x] `useSWR<Product[]>("/api/proxy/items", fetcher)` — no `refreshInterval` (SSE replaces it entirely for this page)
- [x] Rename `Listing`/`Product`/`WatchStatus` types to match real snake_case schema (per `schema.md`) — done together with the two items above; the mock array, the useSWR call, and the type rename don't type-check independently (mock data and JSX both reference old field names against whichever `Product`/`Listing` shape is active), so this section landed as one edit rather than three sequential ones
- [x] Thread `number` IDs through `openId` state, `Sheet` `key`, dropdown action handlers (currently assume `string`)
- [x] Delete `stalestCheckedAt()` (`page.tsx:173-174`) — use `product.last_checked` directly, server-computed
- [x] Null-guard `bestPrice()` — filter out listings with `last_price: null` before `Math.min`; returns `null` (not a crash) when every listing is null, callers render `—`
- [x] Null-guard `formatLastChecked()` — fallback display (`—`) when `last_checked: null`
- [x] Add loading state (mock data could never fail/be pending) and error state for the fetch — both as early returns before the main render
- [x] Empty-table state (mock always had 4 items, currently untested) — single-row `colSpan={8}` fallback when `filtered.length === 0`
- [x] Search/sort: rename `createdAt` → `created_at` in `filtered` (page.tsx:311-313), logic otherwise unchanged

### 4. Frontend — price history (folds in former #10.3)
- [x] `useListingHistory(listingId)` hook — `useSWR` against `/api/proxy/items/{pid}/listings/{lid}/history?days=30`, no `refreshInterval`. Real signature is `useListingHistory(productId, listingId)` — the backend route requires `product_id` in the path (404 ownership check), not just `listingId` as originally written here; callers holding a full `Listing` already have both. `bucketByLocalDay()` co-located in the same file (`frontend/src/lib/hooks/use-listing-history.ts`).
- [x] Table row: child component per row (`ProductRow`) — but a row alone doesn't satisfy rules-of-hooks, since a product's listing count varies; added a second layer, `ListingHistoryFetcher` (one instance per listing, each calling `useListingHistory` exactly once, renders nothing), reporting bucketed results up into `ProductRow`'s own `historyByListing` state. `mergeMinByDay()` (renamed from `productPriceHistory()`) reads that state instead of an embedded `listing.priceHistory` field.
- [x] Sheet chart: same `historyByListing` state as the row's sparkline — not a second fetch, both consumers of one `ProductRow`-owned map, since the sheet only exists inside the row it belongs to. `ProductPriceChart` unchanged, fed `product.listings.map(l => ({retailer, priceHistory: historyByListing[l.id] ?? []}))`.

### 5. Frontend — SSE consumption
- [x] Manual `EventSource` lifecycle, owned by whichever tab wins leader election — lives entirely inside `frontend/src/lib/sse-leader.ts`'s `connect()`, called only from the Web Locks callback; the page component's `useEffect` looks identical regardless of leader/follower role, since `subscribeToListingEvents()` hides that distinction from its caller. Not relying on native auto-reconnect — `es.close()` inside `onerror` hands control fully to the manual backoff.
- [x] `onmessage`: parse `{product_id, listing_id}`, `mutate("/api/proxy/items")` + `mutate(listingHistoryKey(product_id, listing_id))` (needed `product_id` too, not just `listing_id` — same gap as §4's hook signature; the event payload already carries it).
- [x] `onopen` → `setStatus("online")` → page's `onStatusChange` triggers the safety-net `mutate("/api/proxy/items")` on every connect/reconnect — same path for the very first connect, a resumed connection, and a newly-promoted leader's fresh connection, no special-casing needed since "online" fires identically either way.
- [x] `onerror`: `es.close()`, schedule reconnect via manual exponential backoff — `1.0s` initial, `×2` per failure, capped at `60.0s`, reset to `1.0s` on next successful open — exact same constants as `backend/app/services/stocks.py`'s `FinnhubClient._listen()` (`_RECONNECT_INITIAL`/`_RECONNECT_MAX`).
- [x] Connection-status UI: `isOnline` (`navigator.onLine`/`online`/`offline` listeners, local to every tab, no relay needed) and `connectionStatus` (`"online" | "unavailable"`, relayed from the leader over `BroadcastChannel` so follower tabs show the real state too) — combined into a single conditional `Badge` in `watchlist/page.tsx`, nothing rendered when both are fine.

### 6. Frontend — multi-tab dedup (leader election)
- [x] New module `frontend/src/lib/sse-leader.ts` — `navigator.locks.request("sse-leader", { signal }, callback)`, called unconditionally by every mounted tab via `subscribeToListingEvents()`. Added an `AbortController` beyond the original sketch: cleanup needs to handle two different cases — a tab that became leader releases the lock (resolves the held promise), a tab still queued as a follower aborts its pending request instead (otherwise it'd leak in the browser's internal lock queue after unmount).
- [x] Leader tab: opens the real `EventSource`, relays every `onmessage` payload **and every status change** out via `new BroadcastChannel("sse-relay")` — status needed relaying too, not just events, so follower tabs' connection-status UI reflects the real connection state rather than always showing nothing.
- [x] Follower tabs: no `EventSource` at all — `channel.onmessage` dispatches to the exact same `onEvent`/`onStatusChange` handlers the leader path uses, via one shared `RelayMessage` union type (`{kind: "event"}` / `{kind: "status"}`).
- [x] On promotion: the same `connect()` function runs regardless of which tab it's running in or when — no separate "promoted" code path exists, the Web Locks queue just calls the same callback whenever a tab reaches the front.
- [x] Scope/rationale: as designed — mitigates the browser's per-origin connection cap. Full comparison in `.doc/keynotes.md`.

### 7. Testing & Validation

Backend automated coverage added (`backend/tests/services/test_sse.py`, `backend/tests/api/test_events_routes.py`, `backend/tests/scheduler/test_jobs.py`) — 39/39 passing, reviewed. Backs the *server-side* mechanism behind items 1, 4, and 5 below (register/unregister accounting, cleanup-on-cancellation, broadcast call-site correctness incl. a regression test for `listing.id` vs `winning.id`) — none of that substitutes for the manual browser checks themselves, which still need the actual frontend/multi-tab/network behavior verified. Still all unchecked below for that reason.

- [x] Manual test: rapid mount/unmount (or toggle React StrictMode) in local dev — confirm backend's fan-out set doesn't grow (no leaked/duplicate connections from the open→close→open double-invoke). Caught a real bug in the process: StrictMode's synchronous mount→cleanup→mount raced against `navigator.locks`' always-async grant — a doomed, already-cleaned-up request could still get granted, hold the lock forever doing nothing (`connect()` no-ops on `closed`), and deadlock every other tab behind it. Fixed in `sse-leader.ts`: the lock callback now checks `closed` itself and releases immediately if it's already too late, rather than assuming an unset `releaseLock` only ever means "never granted."
- [x] Manual test: kill backend mid-connection, confirm exponential backoff (not fixed 3s hammering) and eventual reconnect once backend's back
- [x] Manual test: disconnect network entirely — confirm "offline" state shows, distinct from "live updates unavailable"
- [ ] Manual test: trigger a manual scrape (`POST /api/poll/prices`), confirm table updates without a page reload and without a 30s wait
- [ ] Manual test: open `/watchlist` in 2+ tabs — confirm backend's fan-out set shows exactly **one** registered connection, not one per tab; close the leader tab, confirm a follower promotes and reconnects within one lock-queue cycle
- [ ] Confirm via browser Network tab: no `X-API-Key` ever appears on any request the browser itself initiates
- [ ] Confirm via browser Network tab: no `refreshInterval`-driven polling requests fire on `/watchlist` at all

### 8. Cleanup
- [x] Remove any leftover `console.log` stubs this issue doesn't intentionally leave behind (mutations stay stubbed per `#10.2` — don't accidentally wire those up here) — audited every file this issue touched; all 7 remaining calls are the pre-existing `#10.2` mutation stubs, nothing new leaked in
- [x] Run `npm run lint` (frontend) and confirm no errors — clean
- [x] Confirm `.doc/architecture.md`'s System Diagram dotted lines (SSE path) can be updated to solid once this ships — updated now (user confirmed doing this ahead of merge/review rather than waiting): diagram lines solid, `BCAST`/`SSEPROXY` node labels de-"proposed", the "Proposed — SSE Push" section renamed to "SSE Push Flow" and rewritten past-tense, multi-tab dedup mechanism added to the prose (wasn't in the original proposal sketch)
