# Issue #51: Implementation

## Steps

### 1. Backend — per-product cooldown state
- [x] In `backend/app/api/items.py`, add module-level `_last_product_trigger: dict[int, datetime] = {}` and a `_PRODUCT_RATE_LIMIT_WINDOW = timedelta(seconds=45)` constant
- [x] Add `_check_product_rate_limit(product_id: int) -> None`, same shape as `poll.py`'s `_check_rate_limit`, raising `HTTPException(429, detail=f"Rate limited, try again in {remaining}s")` when inside the window

### 2. Backend — new route
- [x] Add `POST /api/items/{product_id}/poll` in `items.py` (named `poll_item`):
  - `await get_product(product_id, db)` to load the product + listings (renamed from `_get_product_or_404`, see the standalone rename commit)
  - Compute `listing_ids = [l.id for l in product.listings]`
  - Zero-listing edge case resolved: no special-case — `_dispatch_first_scrapes` on an empty list is a no-op `gather()` that returns immediately, still 200s with `status="queued"`
  - If any `listing_ids` intersect `in_flight_snapshot()` → `raise HTTPException(429, detail="Already scraping — try again shortly")`
  - Else `_check_product_rate_limit(product_id)` (429 on cooldown)
  - Else record `_last_product_trigger[product_id] = datetime.now(timezone.utc)`, `spawn(_dispatch_first_scrapes(listing_ids, _first_scrape_semaphore, request.app.state.event_queue))`, return `{"status": "queued"}`

### 3. Frontend — data layer
- [x] In `frontend/src/lib/api/items.ts`, add `pollAllPrices()` and `pollProduct(productId)` (see schema.md for exact signatures)

### 4. Frontend — global button
- [x] In `watchlist/page.tsx` toolbar, next to "New item", add an icon button (`RefreshCw`, `aria-label="Rescrape all"`), disabled for the click-to-response gap via local `isRescrapingAll` state
- [x] `onClick`: `try { await pollAllPrices(); toast.success("Rescraping…"); } catch (err) { toast.error(err instanceof ApiError ? err.detail : "Failed to trigger rescrape"); }`
- [x] No manual `mutate()` call needed — existing SSE flow already refreshes `/api/proxy/items` as results land

### 5. Frontend — per-item button
- [x] In the sheet panel's "Retailers" row, add a second icon button (`RefreshCw`, `aria-label="Rescrape {product.name ?? 'item'}"`) next to the existing "Add retailer" `+` button, both right-aligned in the existing `justify-between` row
- [x] `disabled` when `isPolling` (local, covers the click-to-response gap) or `product.status === "processing"` (covers the actual scrape duration via the existing in-flight-aware status)
- [x] `onClick`: same try/catch/toast pattern as the global button, calling `pollProduct(product.id)`

### 6. Testing & Validation
- [ ] Manual test: click global button, confirm "Rescraping…" toast, confirm rows update to "processing" then resolve via SSE with no page reload
- [ ] Manual test: click global button twice within 5 minutes, confirm the second click surfaces the existing cooldown message (not a generic error)
- [ ] Manual test: click a per-item button, confirm only that product's listings show "processing", others untouched
- [ ] Manual test: click the same per-item button twice rapidly, confirm the second click is rejected (429) rather than queuing a duplicate scrape
- [ ] Manual test: click per-item button, confirm it's disabled while in flight and re-enables once the SSE update lands
- [ ] Edge case: product with zero listings — confirm the per-item route's chosen behavior (404 or no-op) matches what was decided in step 2
- [ ] Regression check: confirm `poll_prices`'s scheduled 6h cycle and #41's add-time first-scrape both still fire correctly (unchanged code paths, but exercised by the same `_dispatch_first_scrapes`/semaphore now under slightly more concurrent callers)

### 7. Cleanup
- [ ] Run `npm run lint` (frontend) and fix errors
- [ ] Confirm no leftover debug logging in the new route
