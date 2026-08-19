# Issue #48: Implementation

Sequenced per advisor guidance: land the schema change as its own complete, tested unit (Phase A) before touching `poll_prices`'s grouping/concurrency (Phase B) or the race fix (Phase C) — writing B/C against the old `Listing.active` model first would mean rewriting them a second time once the schema lands.

## Phase A — `Product.active` schema change (do first)

### A1. Migration
- [x] Created `backend/alembic/versions/0012_product_active_drop_listing_active.py` (revises `0011`) — exact content in `schema.md`. Adds `products.active` (default true), backfills (`false` where product has zero active listings under the old model), drops `watch_items.active`. `alembic history` confirms the chain resolves (`0011 -> 0012 (head)`).
- [ ] **Still pending — needs you:** run it against local Postgres (`docker-compose.local.yml` up, then `cd backend && uv run alembic upgrade head`). Not yet applied to any real database.

### A2. Models
- [x] `backend/app/models/product.py` — added `active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")`; added `Boolean` to the `sqlalchemy` import.
- [x] `backend/app/models/watch_item.py` — removed the `active` column line and the now-unused `Boolean` import.

### A3. `compute_status`
- [x] `backend/app/services/product_status.py` — signature is now `compute_status(listings, product_active, alerted_at)`; simplified body, no more `active_listings` filtering.
- [x] Call site in `items.py::_build_product_response`: `compute_status(product.listings, product.active, product.alerted_at)`.

### A4. Schemas
- [x] `backend/app/schemas/product.py` — `ProductUpdate` gained `active: bool | None = None`.
- [x] `backend/app/schemas/listing.py` — `ListingUpdate` and `ListingResponse` both lost `active`.

### A5. Routes (`backend/app/api/items.py`)
- [x] `update_item`: writes `product.active` when provided; docstring updated to describe the cascade behavior.
- [x] `update_listing`: dropped its `active` handling block; docstring/summary updated (no longer claims to pause/unpause).
- [x] `_build_listing_response`: dropped `active=listing.active`.
- [x] Confirmed via grep — no remaining `.active` reference on `Listing`/`listing` anywhere in `items.py`.

### A6. Frontend
- [x] `frontend/src/lib/api/items.ts` — `Listing.active` removed; `ListingUpdatePayload.active` removed; `ProductUpdatePayload.active` added.
- [x] `frontend/src/app/watchlist/page.tsx` — Switch's `onCheckedChange` is now a single `updateProduct(product.id, { active })` call, no more `Promise.allSettled` fan-out or the "N of M retailers failed" toast branch.
- [x] `npx tsc --noEmit` passes clean.

### A7. Tests
- [x] `backend/tests/services/test_product_status.py` — updated `_listing` helper (dropped `active` param), every `compute_status(...)` call now passes `product_active`. Deleted the two per-listing-independence tests. Renamed `test_compute_status_all_inactive_is_paused` → `test_compute_status_product_inactive_is_paused`.
- [x] `backend/tests/api/test_items_routes.py` — `_listing`/`_product` fixtures updated (`active` moved from `_listing` to `_product`); `test_update_listing_pauses` deleted, replaced with `test_listing_update_silently_ignores_active_field` (confirms Pydantic drops the unknown field, not 422) and `test_update_item_toggles_active` (confirms the real product-level toggle + resulting `status`). Also: the moved-function unit tests (`test_dispatch_first_scrapes_*`, `test_bounded_process_item_*`) were relocated to `test_jobs.py` with corrected `app.scheduler.jobs.*` patch targets — leftover fallout from the earlier helper-move step that hadn't been test-verified until now.

**Correction to the original phase split:** `jobs.py`'s `process_item`/`poll_prices` reference `Listing.active` as a *live SQLAlchemy column*, not just test data — dropping the column breaks them at runtime regardless of whether Phase B/C's grouping or lock work has landed. So the mechanical fix (early bail → column-only `Product.active` check; `poll_prices`'s query → join on `Product.active`; cross-listing filter → drop the clause) had to land in Phase A, not wait for Phase C as originally planned. Scope stayed minimal though — no grouping, no `with_for_update()`, no concurrency; those still wait for Phase B/C. This pulled `test_jobs.py`'s fixture/test updates into Phase A too, for the same reason (its `_listing`/`_product` mocks and `session.execute` mocking now have to match the changed early-bail code path). What's still deferred to Phase C: only the `with_for_update()` upgrade to the *second* Product read (the alert-dedup fix itself), plus the grouping/concurrency dispatch logic.
- [x] Full backend suite: **313 passed**. Frontend `tsc --noEmit`: clean.

## Phase B — Group `poll_prices` by product (original issue, adjusted for `Product.active`) — ✅ done

- [x] Query changed: `select(Listing.id, Listing.product_id).join(Product, Listing.product_id == Product.id).where(Product.active == True)`.
- [x] Results grouped into `listings_by_product: dict[int, list[int]]` client-side (plain dict, insertion order — no `ORDER BY` needed).
- [x] Loop restructured: outer loop over `product_id, listing_ids` (still one product after another), inner loop over that product's own `listing_ids` (still one at a time — the *concurrency* part is Phase C, this phase is only the grouping/ordering fix). `close_if_idle()` still fires once, after both loops, unchanged.
- [x] `test_jobs.py`'s three `poll_prices` tests updated (`_rows_result` helper added — the query now returns `(listing_id, product_id)` tuples via `.all()`, not a flat id list via `.scalars().all()`).
- [x] Full backend suite: 313 passed.

## Phase C — Per-product concurrent dispatch + the race fix — ✅ done

- [x] ~~Move `_bounded_process_item`/`_dispatch_first_scrapes` from `items.py` to `jobs.py`~~ — **done** (see below, completed before the schema-change scope expansion; unaffected by Phases A/B).
- [x] `_poll_concurrency_semaphore = asyncio.Semaphore(3)` (`_POLL_CONCURRENCY = 3`) added module-level in `jobs.py` — separate instance from `items.py`'s `_first_scrape_semaphore`, same cap value, per the separate-pools decision.
- [x] Flat loop replaced: iterate `product_id, listing_ids` from Phase B's grouped dict sequentially, `await _gather_bounded_scrapes(listing_ids, _poll_concurrency_semaphore, queue)` per product (a listing's own scrapes now run concurrently, bounded).
- [x] `close_if_idle()` call-count mismatch resolved via option (a): `_dispatch_first_scrapes` split into `_gather_bounded_scrapes` (the `gather()` alone) + itself (wraps it with `close_if_idle()`, for `items.py`'s two call sites, unchanged behavior there). `poll_prices` calls `_gather_bounded_scrapes` directly per product, then its own single `close_if_idle()` once after the full loop.
- [x] `process_item`'s alert-dedup race fix: `product = await session.get(Product, listing.product_id)` → `select(Product).where(Product.id == listing.product_id).with_for_update()` via `session.execute(...).scalar_one()`. Sits after the scrape (lock only held for the tail). Identity-map safety intact — the early-bail check (Phase A) is column-only, never touches the identity map.
- [x] `backend/tests/scheduler/test_jobs.py` — `_product_result` helper added; `session.get`/`session.execute` mock sequences updated for the locked second Product read (`session.get` now returns only the `Listing`; `session.execute`'s side-effect list grew a third/middle entry). The two `poll_prices` tests with stale concurrency assumptions fixed: `test_poll_prices_closes_browser_once_after_full_cycle` now asserts `close` is last + the three `process:N` happened before it (set, not exact sequence — they're concurrent now), docstring corrected; `test_poll_prices_continues_when_item_processing_errors` got a docstring note that the error-swallowing mechanism now lives in `_bounded_process_item`, not `poll_prices`' own loop.
- **A real test was attempted and deliberately dropped** — see `challenges.md` #4 for the full account. An end-to-end `asyncio.gather`-based race simulation (two `process_item` calls sharing a mocked lock/DB state) passed identically whether or not the lock was simulated at all, because there's no `await` between the `alerted_at` check and the write in `process_item` — no mock-injected yield can ever demonstrate the race in a single-threaded event loop; whichever task's resume reaches that region always completes it atomically first. Keeping that test would have been actively misleading (reads as "race covered," isn't). What's unit-tested instead, in `test_process_item_writes_history_and_price_drop_event`: the second `session.execute` call carries `_for_update_arg is not None`, and `session.get` is awaited exactly once (only the `Listing`, never a plain `session.get(Product, ...)`) — this breaks the moment someone reverts the fix. The race itself is only genuinely provable against a real Postgres — that's this issue's own live-verification AC, not a gap this phase left open.
- [x] Full backend suite: 313 passed.

## Testing & Validation
- [ ] Unit/manual: single-listing product through `poll_prices` — confirm identical behavior to before (no grouping/concurrency effect when a product has exactly one listing).
- [ ] Manual (you — Docker/deploy steps are user-run): deploy to Pi, pick or create a product with 2+ listings, force both under target price before a cycle runs, trigger/wait for `poll_prices`, confirm **exactly one** `Event` row + one push notification, not two.
- [ ] Manual: re-run #41's bulk-add scenario (add a product with several URLs, 2+ already under target on first scrape) and confirm still exactly one alert.
- [ ] Manual: pause a product via the watchlist Switch, confirm it stops appearing in `poll_prices`'s next cycle grouping.
- [ ] Manual: measure `poll_prices` cycle wall-clock (log timestamps at "starting cycle" / "cycle complete") before and after, on the real dataset.

## Cleanup
- [x] Remove now-dead imports in `items.py` if `RetailerRouter`/`PatchrightScraper` were only used by the moved functions — done during the helper-move step.
- [x] Re-checked `jobs.py`'s imports after Phase C — `RetailerRouter` still used (type hint + `_bounded_process_item`'s fresh-instance-per-call); `with_for_update` is a method, no separate import needed; nothing dead.

---

## Completed: helper move (`_bounded_process_item` / `_dispatch_first_scrapes`)
- [x] Cut `_bounded_process_item` and `_dispatch_first_scrapes` out of `backend/app/api/items.py`, paste into `backend/app/scheduler/jobs.py`.
- [x] Reworded their docstrings to reflect both callers (#41's request-triggered path, `poll_prices`'s scheduled cycle).
- [x] `items.py` imports `_dispatch_first_scrapes` from `app.scheduler.jobs` (confirmed `_bounded_process_item` isn't referenced directly outside it). Dropped now-dead `RetailerRouter`/`PatchrightScraper` imports from `items.py`.
- [x] `items.py` keeps its own `_first_scrape_semaphore = asyncio.Semaphore(3)` untouched.
- Verified: `python3 -m py_compile` on both files passes. Runtime/import check still pending your Docker env.
