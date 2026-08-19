# Issue #48: Per-Product Concurrent Polling + Fix the Latent Double-Alert Race

**Scope note:** expanded mid-planning beyond the original issue text. Grilling step 2 (grouping `poll_prices` by product) surfaced that `Listing.active` — the field the grouping/filtering logic was going to key off — is a per-listing flag that's only ever exercised in lockstep across a whole product (one UI toggle, `Promise.allSettled` over every listing) despite backend logic and tests treating it as independently settable per listing. Decision (confirmed with user): consolidate to a real `Product.active` column, drop `Listing.active` entirely. This folds a schema change into #48 rather than deferring it.

## PR / Branch
- **Branch:** `fix/48-per-product-concurrent-polling`
- **PR Title:** `main | fix - 48 - Per-product concurrent polling, product-level active, double-alert race fix`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & Data Model | 🔶 Code done, migration not yet applied to a real DB | [schema.md](schema.md) |
| Implementation | ✅ Phases A/B/C all done (code + unit tests) | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria

### Original issue #48
- [x] `poll_prices`'s query groups active listings by product (not the flat unordered `select(Listing.id)`)
- [x] A product's own listings scrape concurrently, bounded by a semaphore (reusing #47/#41's gather-with-semaphore shape); products themselves still processed one at a time (`_prices_lock` cycle-safety preserved)
- [x] `product.alerted_at` read-then-write race fixed via `SELECT ... FOR UPDATE` inside `process_item` — code + SQL-shape unit tests done. **Still open:** live verification (a product with 2+ listings crossing target price in the same cycle fires exactly one `Event`/notification) — genuinely only provable against a real Postgres, see `challenges.md` #4; this is on you.
- [x] Same fix protects #41's existing concurrent bulk-add path too — one guard, one fix site (both call sites funnel through `process_item`), not two
- [x] No behavior change for single-listing products (the common case) — unaffected by grouping/concurrency when a product has exactly one listing
- [ ] `poll_prices` cycle wall-clock time measured before/after on a real multi-product, multi-listing dataset — needs your deployment, not yet done

### Folded-in schema change
- [x] `Product.active` column + migration written, backfill logic confirmed lossless against real data (empty-result diagnostic). **Still open:** migration not yet run anywhere (needs `alembic upgrade head` on your local Postgres) — see `implementation.md` Phase A1.
- [x] `Listing.active` column dropped (in the migration + model)
- [x] `compute_status` reads `product.active` directly; status derivation behavior unchanged for every currently-possible state (confirmed via the same lossless-migration property — no product can reach a status it couldn't before)
- [x] `PATCH /api/items/{id}` toggles `active`, cascades to pausing scraping for every listing under it (via `poll_prices`'s `Product.active` join)
- [x] `PATCH /api/items/{id}/listings/{id}` no longer accepts `active`
- [x] Watchlist page's pause Switch does one `updateProduct` call instead of fanning out over every listing
- [x] Full backend test suite green (313 passed) after removing/rewriting the tests built around independent per-listing active

## Estimated Effort
- Schema change (migration, models, schemas, routes, frontend, tests): **~3 hours** — done
- Original #48 (grouping, concurrency, race fix): **~2.5 hours** — done
- **Total: ~5.5 hours** — code complete; remaining work is you running the migration + the three manual live-verification steps
