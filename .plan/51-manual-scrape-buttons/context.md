# Issue #51: Context

## Issue Description

Two separate pieces, both letting a user force a scrape right now instead of waiting for the next scheduled 6h `poll_prices` cycle:

- **Global** — a button that rescrapes the whole watchlist. Backend already exists (`POST /api/poll/prices`, from #6); nothing frontend calls it today.
- **Per-item** — a button in the product's sheet panel that rescrapes only that product's own listings. Needs a new backend endpoint; nothing per-item exists today.

Prompted by this session's musinsa/29CM investigation — wanting a fresh price check right after fixing/adding a listing, instead of waiting up to 6h.

### Acceptance criteria
- [ ] Global button calls `POST /api/poll/prices`, surfaces the 429 cooldown message instead of a generic error, and results show up via the existing SSE refresh without a manual page reload
- [ ] New `POST /api/items/{product_id}/poll` route rescrapes only that product's own listings, reusing `_dispatch_first_scrapes` — not a second scraping implementation
- [ ] Manually-triggered re-scrape shows `"processing"` on the affected row/sheet via existing `compute_status()`, no changes needed to that function
- [ ] Rapid repeat clicks on the same product's button don't queue redundant concurrent scrapes of the same listings — rate-limit strategy decided and implemented, not left as a TODO
- [ ] Sheet-panel button disables while its own product's listings are in flight; re-enables once the SSE update lands
- [ ] No regression to `poll_prices`'s own 6h schedule or #41's add-time first-scrape — both still work unchanged

## Component / Route Summary

### Current State

- `backend/app/api/poll.py` — `POST /api/poll/prices` already exists (module-level `_last_prices_trigger: datetime | None`, 5-minute rate limit, 429 with remaining-seconds detail). Runs `poll_prices` as a `BackgroundTasks` task. Confirmed: no reference to `poll/prices` anywhere in `frontend/src`.
- `backend/app/scheduler/jobs.py` — `_dispatch_first_scrapes(listing_ids, semaphore, queue)` (line 346) already does exactly what a per-item manual scrape needs: bounded `gather()` over `_gather_bounded_scrapes`, then `PatchrightScraper.close_if_idle()`. Shared today between `create_item`/`create_listing` (#41's add-time first-scrape, `items.py`) and used as the building block for `poll_prices`'s own per-product batches.
- `backend/app/services/scrape_tracking.py` — `mark_in_flight`/`clear_in_flight`/`in_flight_snapshot()` already track which listing ids are mid-scrape, process-local, in-memory. `compute_status()` (`product_status.py`) already checks this set and returns `"processing"` — zero changes needed there for this issue.
- `backend/app/api/items.py` — owns `_first_scrape_semaphore` (`asyncio.Semaphore(3)`, line 61), the pool #41's add-time scrapes run under.
- `frontend/src/app/watchlist/page.tsx` — toolbar with search + "New item" `+` button (lines 912-919); stat row (Items/Triggered/Watching, lines 945-966); sheet panel's "Retailers" section header with an existing "Add retailer" `+` icon button in a `justify-between` row (lines 515-521). SSE flow already exists: `subscribeToListingEvents` → `mutate("/api/proxy/items")` (line 808-820), fires on every listing event without any polling loop.
- `frontend/src/lib/api/items.ts` — thin fetch wrapper (`request<T>`) over `/api/proxy/items`, one named function per write path. No poll-related function exists yet.
- `frontend/src/app/api/proxy/[...path]/route.ts` — generic catch-all proxy (GET/POST/PATCH/DELETE), forwards any `/api/proxy/{path}` to the backend with the `X-API-Key` header attached. No new proxy route needed for either new call — it's already a catch-all.

**Note on the issue's own rate-limit proposal:** the issue text suggests keying a per-product cooldown off "`Product.last_checked`/listing `last_scrape_status` timestamps" — neither exists as a literal timestamp. `Product` has no `last_checked` column (it's computed on the fly by `compute_last_checked()` from `PriceHistory.checked_at`); `Listing.last_scrape_status` is a string status enum (`"ok" | "oos" | "error" | None`), not a time value. Resolved via grill-me: use a dedicated in-memory `dict[int, datetime]` keyed by `product_id`, mirroring `poll.py`'s existing single-value pattern instead of querying `PriceHistory` or adding a column.

### Target State

- New `POST /api/items/{product_id}/poll` route in `items.py`: looks up the product's listing ids, checks (a) `in_flight_snapshot()` for overlap and (b) a new per-product cooldown dict (45s window), 429s with a distinguishing `detail` message on either rejection, otherwise `spawn(_dispatch_first_scrapes(listing_ids, _first_scrape_semaphore, request.app.state.event_queue))` and returns `{"status": "queued"}` — same shape as `trigger_poll_prices`.
- `frontend/src/lib/api/items.ts` gains two new functions: `pollAllPrices()` (POSTs `/api/proxy/poll/prices`) and `pollProduct(productId)` (POSTs `/api/proxy/items/{id}/poll`).
- `watchlist/page.tsx` toolbar gains a global rescrape icon button next to "New item"; the sheet panel's "Retailers" row gains a per-item rescrape icon button next to "Add retailer", disabled while any of that product's listings are in the in-flight set (already exposed per-product via `product.status === "processing"`, or a direct check against listing ids — see implementation.md).
- Both buttons: `toast.success("Rescraping…")` on 202/200, `toast.error(detail from 429 body)` on rate-limit, no new fetch/poll loop — same SSE-driven refresh already wired for every other mutation on this page.

## Impact & Risk

### Files Changed
- **`backend/app/api/items.py`** — new `POST /api/items/{product_id}/poll` route, new per-product cooldown dict + check function
- **`frontend/src/lib/api/items.ts`** — two new exported functions (`pollAllPrices`, `pollProduct`)
- **`frontend/src/app/watchlist/page.tsx`** — two new buttons (toolbar + sheet panel), wired to the new functions and existing toast/SSE patterns

### Dependencies
- **`_dispatch_first_scrapes` / `_first_scrape_semaphore`** (`items.py`, `jobs.py`) — reused as-is, no changes
- **`in_flight_snapshot()`** (`scrape_tracking.py`) — reused as-is for the in-flight guard
- **`subscribeToListingEvents` / SWR `mutate`** (`sse-leader.ts`, `page.tsx`) — reused as-is for the post-trigger refresh

### Breaking Changes
None — purely additive (one new backend route, two new frontend functions, two new buttons).
