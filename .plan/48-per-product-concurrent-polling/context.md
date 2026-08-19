# Issue #48: Context

## Issue Description
Full text: `.doc/issues.md#L2590-2625`. **Scope expanded during planning** — see `_index.md`'s scope note and `schema.md`: grouping `poll_prices` by product surfaced that `Listing.active` (the natural grouping/filter key) is only ever toggled in lockstep across a whole product, never independently in practice, despite the schema and several tests modeling it as independent. Decision: consolidate to `Product.active`, drop `Listing.active`. That schema change is folded into this issue rather than deferred.

`poll_prices` (`backend/app/scheduler/jobs.py`) queries every active listing as one flat, ungrouped list (`select(Listing.id).where(Listing.active == True)`, no ordering) and processes them one at a time. A product's own listings can land anywhere in that flat order — processed hours apart within the same nominal cycle. `process_item`'s cross-listing price comparison reads whatever `last_price` is *currently in the DB* for a product's sibling listings, so today's arbitrary ordering can compare a fresh-this-cycle price against an hours-stale one from earlier in the same cycle.

**Fix:** group the query by product, iterate products sequentially (preserves `_prices_lock`'s whole-cycle serialization), scrape each product's own listings concurrently via `asyncio.gather()` bounded by a semaphore — same shape as #47/#41's `_dispatch_first_scrapes`/`_bounded_process_item`.

**Must ship together:** `process_item` opens an independent `AsyncSessionLocal()` per listing and does its own `session.get(Product, ...)`. Two listings of the same product scraped concurrently can both read `product.alerted_at is None` before either commits — both fire, both write an `Event`, double notification. Already latent today in #41's bulk-add path (rare coincidence there); this issue's change turns it into something that fires for real, unattended, every 6h.

## Component / Route Summary

### Current State
- `poll_prices` (`jobs.py:23`): flat `select(Listing.id)`, sequential single-listing loop, `close_if_idle()` once at cycle end.
- `process_item` (`jobs.py:76`): per-listing session; early bail is `if not listing or not listing.active: return` (listing-level); scrapes; on success, plain `product = await session.get(Product, listing.product_id)` (no lock); compares against sibling listings currently in DB, filtered by `Listing.active == True`; alert-dedup via `if cheapest <= product.target_price and product.alerted_at is None`.
- `_bounded_process_item` / `_dispatch_first_scrapes` (`items.py:200-256`): #41's existing gather-with-semaphore shape, semaphore-bounded concurrent scrape dispatch, `close_if_idle()` after the whole batch. Currently only reachable from `create_item`/`create_listing`.
- `_first_scrape_semaphore = asyncio.Semaphore(3)` (`items.py:62`), module-level, scoped to #41's add-time path only.

### Target State
- `_bounded_process_item` and `_dispatch_first_scrapes` **move** from `items.py` to `jobs.py`. `items.py` imports them back (no new circularity — it already imports `process_item` from `jobs.py`). Single shared implementation, not two copies.
- `poll_prices` groups listing ids by `product_id` in Python (query still one `SELECT`, grouped client-side into `dict[int, list[int]]`), iterates products sequentially, and for each product calls the (now-shared) dispatch helper with its own semaphore instance (`_poll_semaphore = asyncio.Semaphore(3)`, separate pool from `items.py`'s `_first_scrape_semaphore` — same value, deliberately separate instance so an add-time burst and a scheduled cycle don't compete for the same slots).
- `process_item`'s early bail becomes product-scoped: a column-only `select(Product.active).where(Product.id == listing.product_id)` (never a full entity load — see `schema.md` for why: it must not populate the session's identity map ahead of the locked read below). Its later `product = await session.get(Product, listing.product_id)` becomes a locking read: `product = (await session.execute(select(Product).where(Product.id == listing.product_id).with_for_update())).scalar_one()`. Lock acquired after the scrape (network I/O) already completed, held only through the alerted_at check + commit — concurrency for the slow part is untouched, only the short critical section serializes per product. Cross-listing comparison drops its `Listing.active == True` filter (field no longer exists) — every listing under an active product participates.
- `close_if_idle()` stays called exactly once, after the full product loop, same as today.

## Impact & Risk

### Files Changed
- **`backend/alembic/versions/0012_*.py`** (new) — adds `products.active`, backfills, drops `watch_items.active`. See `schema.md`.
- **`backend/app/models/product.py`** — adds `active` column.
- **`backend/app/models/watch_item.py`** — removes `active` column.
- **`backend/app/services/product_status.py`** — `compute_status` signature/body changed to read `product.active` directly.
- **`backend/app/schemas/product.py`** — `ProductUpdate` gains `active`.
- **`backend/app/schemas/listing.py`** — `ListingUpdate`/`ListingResponse` lose `active`.
- **`backend/app/api/items.py`** — `update_item` writes `product.active`; `update_listing` drops its `active` handling; drop `_bounded_process_item`/`_dispatch_first_scrapes` definitions, import them from `app.scheduler.jobs` instead; `_first_scrape_semaphore` stays local, unchanged value/behavior.
- **`backend/app/scheduler/jobs.py`** — query grouped by product via a `Product.active` join; per-product bounded concurrent gather; `_bounded_process_item`/`_dispatch_first_scrapes` moved in; own semaphore constant; `process_item`'s early bail becomes a column-only `Product.active` check (identity-map-safe, see `schema.md`); its later Product read for the alert-dedup fix switched to `with_for_update()`; cross-listing comparison query drops its `Listing.active` filter.
- **`frontend/src/lib/api/items.ts`** — `Listing.active` removed, `ProductUpdatePayload.active` added, `ListingUpdatePayload.active` removed.
- **`frontend/src/app/watchlist/page.tsx`** — pause Switch's `onCheckedChange` becomes a single `updateProduct` call instead of fanning out over every listing.
- **`backend/tests/services/test_product_status.py`**, **`backend/tests/scheduler/test_jobs.py`**, **`backend/tests/api/test_items_routes.py`** — tests built around independent per-listing active removed/rewritten (see `challenges.md`).

### Dependencies
- **`PatchrightScraper.close_if_idle()`** — unchanged call site count and placement (once per whole `poll_prices` cycle); its global `_active_scrapes` counter already tolerates overlapping callers (poll cycle + add-time batch), no change needed there.
- **`_prices_lock`** — still guards the whole `poll_prices` cycle; products remain sequential relative to each other, only within-product listings go concurrent.
- **Postgres `SELECT ... FOR UPDATE`** — confirmed engine is Postgres (`backend/app/core/db.py` + NAS-hosted Postgres per project setup), row-level locking is directly supported, no dialect workaround needed.

### Breaking Changes
- `PATCH /api/items/{id}/listings/{id}` no longer accepts `active` — any external caller pausing an individual listing via that field breaks. No known external callers beyond this app's own frontend (confirmed: the only pause control in the UI already wrote to every listing at once).
- `ListingResponse` drops the `active` field — any consumer reading it (frontend `Listing` type, tests) needs updating.
- Migration `0012` is one-way lossy on `downgrade()` for any partial per-listing state (see `schema.md`'s downgrade note) — acceptable since forward migration was confirmed lossless for current data, and downgrade is a best-effort rollback path, not an expected operation.
- `poll_prices` external behavior for single-listing products (the common case) is unchanged beyond the `Listing.active` → `Product.active` filter switch; only ordering/grouping and the alert-dedup guard change internally otherwise.
