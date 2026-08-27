# Issue #51: Implementation

## Steps

### 1. Backend — per-product cooldown state
- [ ] In `backend/app/api/items.py`, add module-level `_last_product_trigger: dict[int, datetime] = {}` and a `_PRODUCT_RATE_LIMIT_WINDOW = timedelta(seconds=45)` constant
- [ ] Add `_check_product_rate_limit(product_id: int) -> None`, same shape as `poll.py`'s `_check_rate_limit`, raising `HTTPException(429, detail=f"Rate limited, try again in {remaining}s")` when inside the window

### 2. Backend — new route
- [ ] Add `POST /api/items/{product_id}/poll` in `items.py`:
  - `await _get_product_or_404(product_id, db)` to load the product + listings (reuses existing helper, 404s correctly)
  - Compute `listing_ids = [l.id for l in product.listings]`
  - If `listing_ids` is empty, decide: 404 or no-op 200 — product with zero listings can't be rescraped (edge case, see challenges.md)
  - If any `listing_ids` intersect `in_flight_snapshot()` → `raise HTTPException(429, detail="Already scraping — try again shortly")`
  - Else `_check_product_rate_limit(product_id)` (429 on cooldown)
  - Else record `_last_product_trigger[product_id] = datetime.now(timezone.utc)`, `spawn(_dispatch_first_scrapes(listing_ids, _first_scrape_semaphore, request.app.state.event_queue))`, return `{"status": "queued"}`

### 3. Frontend — data layer
- [ ] In `frontend/src/lib/api/items.ts`, add `pollAllPrices()` and `pollProduct(productId)` (see schema.md for exact signatures)

### 4. Frontend — global button
- [ ] In `watchlist/page.tsx` toolbar (near line 912-919, next to "New item"), add an icon button (`RefreshCw`, `aria-label="Rescrape all"`)
- [ ] `onClick`: `try { await pollAllPrices(); toast.success("Rescraping…"); } catch (err) { toast.error(err instanceof ApiError ? err.detail : "Failed to trigger rescrape"); }`
- [ ] No manual `mutate()` call needed — existing SSE flow already refreshes `/api/proxy/items` as results land

### 5. Frontend — per-item button
- [ ] In the sheet panel's "Retailers" row (line 515-521), add a second icon button (`RefreshCw`, `aria-label="Rescrape {product.name ?? 'item'}"`) next to the existing "Add retailer" `+` button, both right-aligned in the existing `justify-between` row
- [ ] `disabled` when any of `product.listings` has its `id` in the current in-flight set — reuse `product.status === "processing"` if that's a sufficient proxy (it already folds in-flight into its check per `compute_status()`), otherwise thread the in-flight ids through if finer-grained disable is needed (see challenges.md)
- [ ] `onClick`: same try/catch/toast pattern as the global button, calling `pollProduct(product.id)`

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
