# Issue #24: Implementation

## Steps

### 1. Pre-flight — ⬜ SKIPPED (deliberate)
- [ ] `pg_dump` snapshot — skipped by user decision. Turned out moot: `watch_items` was empty on the NAS (nothing had ever written a real item through the API — frontend's still on mock data), so there was no existing data at risk.

### 2. Models — ✅ Done
- [x] Create `app/models/product.py` — `Product` class, per [schema.md](schema.md)
- [x] Rename `WatchItem` -> `Listing` in `app/models/watch_item.py` (file path stays `watch_item.py`)
- [x] Add `product_id` (FK, not null) and `last_scrape_status` columns to `Listing`
- [x] Remove `name`, `target_price`, `alerted_at` from the `Listing` ORM class declaration (columns stay in the DB — see migration)
- [x] Add `Product.listings` / `Listing.product` relationship
- [x] Update `app/models/price_history.py`'s `watch_item` relationship type hint reference (`"WatchItem"` -> `"Listing"`)
- [x] Update `app/models/__init__.py` to export `Product`/`Listing`

### 3. Migration — ✅ Applied to NAS, verified
- [x] Write `alembic/versions/0009_product_listing_split.py` per [schema.md](schema.md)'s 9-step upgrade / reversible downgrade
- [x] `alembic history` confirms `0008 -> 0009 (head)` — chain resolves cleanly
- [x] Applied directly to the real NAS DB (`alembic upgrade head` from `backend/`, venv activated) — no local dry-run (skipped along with the pg_dump, per user decision); ran clean, no errors, `0007 -> 0008 -> 0009` all applied in one pass (0008 hadn't been applied yet either)
- [x] Row counts verified: `products` = `watch_items` = 0 (table was empty pre-migration — no real data existed yet, so the backfill had nothing to copy and nothing to get wrong)
- [x] Schema verified via `information_schema.columns`: `products` has exactly the 5 expected columns; `watch_items` gained `product_id` (NOT NULL, FK) and `last_scrape_status` (nullable), while `name`/`target_price`/`alerted_at` remain untouched and unused, as planned for Migration B to drop later

### 4. Schemas — ✅ Done
- [x] Create `app/schemas/product.py` — `ProductCreate`, `ProductUpdate`, `ProductResponse`
- [x] Create `app/schemas/listing.py` — `ListingCreate`, `ListingUpdate`, `ListingResponse`
- [x] Delete `app/schemas/watch_item.py`, update `app/schemas/__init__.py` exports

### 5. Status/last-checked computation helper — ✅ Done
- [x] `app/services/product_status.py` — `compute_status()`, `compute_last_checked()`, standalone pure functions
- [x] `last_checked` query shape: one grouped `func.max` query per request (`_fetch_last_checked_map` in `items.py`), not N+1

### 6. API routes (`app/api/items.py` — full rewrite) — ✅ Done
- [x] All 9 routes from [schema.md](schema.md) implemented
- [x] Shared `_resolve_retailer_and_scraper_type()` helper extracted, used by both POST endpoints

### 7. Scheduler (`app/scheduler/jobs.py`) — ✅ Done
- [x] `_process_item` rewritten: persists `last_scrape_status` on every outcome (`ok`/`oos`/`error`), recomputes cheapest *active* listing across the whole product on every scrape, sets/clears `Product.alerted_at`
- [x] Event payload carries `product_id`, winning listing's `id`/`retailer`/`url`

### 8. Notifications (`app/consumers/notify.py`) — ✅ Done
- [x] `_format_price_drop` looks up `Product`, names the winning retailer in the body

### 9. Docs — ✅ Done
- [x] `.doc/api.md` — "Wishlist Items" section rewritten (routes, computed-fields note)
- [x] `.doc/PRD.md` — removed the now-reversed "no cross-retailer price comparison" out-of-scope line; updated the `WatchItem` -> `Product`/`Listing` model mentions

### 10. Testing — ✅ Done (mocked unit tests); ⬜ migration test NOT done
- [x] `tests/api/test_items_routes.py` rewritten — product routes + listing routes, 28 tests
- [x] `tests/scheduler/test_jobs.py` rewritten — includes the exact re-arm bug scenario from [context.md](context.md) as a dedicated test, plus oos/error persistence, plus a paused-sibling-doesn't-count test
- [x] `tests/consumers/test_notify.py` and `tests/consumers/test_dispatcher.py` updated for `Product` lookup + retailer-naming body
- [x] `tests/services/test_product_status.py` — new, table-tests every `compute_status` priority branch + `compute_last_checked` edge cases
- [x] Full suite: 233 passed
- [ ] Migration upgrade/downgrade test against a real DB — **not done, no Postgres reachable in this sandbox**; run this before applying `0009` anywhere real

### 11. Cleanup — ✅ Done
- [x] `app/schemas/watch_item.py` deleted, no remaining stale `WatchItem` imports anywhere in `app/` (verified via grep)
- [x] `backend/` has no lint/type-check tool configured (only `[tool.pytest.ini_options]` in `pyproject.toml`) — full `pytest` suite passes (233 passed)
