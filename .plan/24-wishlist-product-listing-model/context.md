# Issue #24: Context

## Issue Description

Splits the flat `WatchItem` model into `Product` (the thing being tracked, one shared target price) + `Listing` (one retailer's URL/price for that product — the Python class formerly named `WatchItem`), so the wishlist can show one row per product with multiple retailer listings grouped underneath, instead of one row per URL.

Full original issue text: `.doc/issues.md` lines 786-833 (Issue #24). Blocks the entire #10.1–#10.5 frontend chain — their original scoping assumed the backend was already ready, which was true for the flat model and is no longer true for the grouped one. `.doc/frontend.md`'s `watchlist/page.tsx` already ships a UI built around the grouped shape (mock data only, no backend wiring), which is what originally surfaced the need for this split.

### Acceptance Criteria (from issue, refined during grill-me — see Success Criteria in [_index.md](_index.md) for the final list)
- [ ] Migration A creates `products` + `product_id` FK on `watch_items`, backfills every existing row as a product-of-one, preserves all existing data (verified against a `pg_dump` snapshot)
- [ ] `GET /api/items` returns products with nested `listings[]`
- [ ] `POST /api/items` supports both "new product" and "add listing to existing product"
- [ ] Editing a product's target price is reflected in alerting for all its listings
- [ ] Price-drop detection compares the cheapest active listing's price against `Product.target_price`, not per-listing
- [ ] Alert dedup/re-arm (`alerted_at`) lives on `Product`, fires once per crossing regardless of which listing triggered it
- [ ] Migration B (dropping the old `watch_items` columns) tracked as a separate follow-up issue, not required for this one to close

## Component / Route Summary

### Current State

`backend/app/models/watch_item.py` — one flat `WatchItem` table (`watch_items`): `id, name, url (unique), retailer, target_price, last_price, alerted_at, scraper_type, active, created_at`. One row = one product at one retailer; no way to group multiple retailers under a shared target price.

`backend/app/api/items.py` — `GET/POST /api/items`, `GET/PATCH/DELETE /api/items/{item_id}`, `GET /api/items/{item_id}/history`, all keyed by the single flat `WatchItem.id`.

`backend/app/scheduler/jobs.py` (`_process_item`) — on each listing's scrape, compares *that listing's own* price to *that listing's own* `target_price`, sets/clears *that listing's own* `alerted_at`.

`backend/app/consumers/notify.py` (`_format_price_drop`) — looks up a `WatchItem` by `payload["watch_item_id"]`, formats the notification from `item.name`/`item.target_price`.

`.doc/database.md` and `.doc/api.md` — both still document the old flat model (now updated as part of this planning session, see below).

`frontend/src/app/watchlist/page.tsx` — already built against the *target* grouped shape (mock `products: Product[]` array, each with `listings: Listing[]`), but wired to zero real endpoints. This is the frontend consumer #10.1 will connect once this issue ships.

### Target State

Two-model split (`Product` + `Listing`), two-phase migration, nested routing (`/api/items/{product_id}` and `/api/items/{product_id}/listings/{listing_id}`), rewritten alerting logic that evaluates the whole product on every scrape, and a server-computed `status`/`last_checked`/per-listing stock indicator. Full detail in [schema.md](schema.md).

`.doc/database.md` has already been updated in this planning session to reflect the target model — treat it as current source of truth alongside this plan.

## Design Decisions From grill-me (this session)

The issue text left six real gaps unresolved; each was worked through and is now locked in:

1. **Route/ID namespace** — nested, not flat. `/api/items/{product_id}` for product ops, `/api/items/{product_id}/listings/{listing_id}` for listing ops. A flat shared ID space breaks the moment product and listing IDs diverge post-migration (independent auto-increment sequences).
2. **Migration A backfill** — confirmed it copies `name`/`target_price`/`alerted_at` from each existing `watch_items` row into a new `products` row with the same `id` (issue text only mentioned reusing the `id`, not copying the data — this was an actual gap, now closed).
3. **`watch_items.name` fate** — follows the same treatment as `target_price`/`alerted_at`: stays on the table post-Migration-A, unused, dropped in Migration B.
4. **`POST` design — two endpoints, not one.** Originally proposed a single `POST /api/items` discriminated by an optional `product_id` in the body; user correctly identified that a product can't exist without at least one listing, which makes a shared polymorphic endpoint awkward (ambiguous response type, ambiguous handling of conflicting fields). Settled on `POST /api/items` (always creates product + first listing) and `POST /api/items/{product_id}/listings` (adds a listing to an existing product, `product_id` from the URL path, never the body).
5. **Alerting rewrite is mandatory, not optional cleanup** — two reasons. Mechanical: `target_price`/`alerted_at` no longer exist on `Listing` at all. Behavioral: a naive "just compare the just-scraped listing's price to the product's target" would incorrectly re-arm the alert when an *unrelated* listing's routine poll comes back above target, even while another listing on the same product is still under target. The fix is recomputing `min(active listings' last_price)` for the whole product on every single scrape, not just evaluating the one listing that was just scraped.
6. **`status` (4 states) vs. stock availability (per-listing) — deliberately separated.** Original proposal folded a 5th `oos` state into product-level `status`; user correctly pushed back that stock availability is inherently per-retailer, not per-product (a product with one out-of-stock and one in-stock listing is still watchable). Landed on: `Listing.last_scrape_status` (`ok`/`oos`/`error`) as a new per-listing column, surfaced independently; product-level `status` stays 4 states (`paused`/`failed`/`triggered`/`watching`), computed via the any/all priority rules in [schema.md](schema.md).

## Impact & Risk

### Files Changed
- **`backend/app/models/watch_item.py`** — new `Product` class; `WatchItem` renamed `Listing`, loses `name`/`target_price`/`alerted_at` from its active field set (columns remain physically, unused), gains `product_id` FK and `last_scrape_status`.
- **`backend/app/api/items.py`** — full rewrite: product-scoped and listing-scoped route groups, two POST endpoints, server-computed `status`/`last_checked` in responses.
- **`backend/app/schemas/watch_item.py`** — new `ProductCreate`/`ProductUpdate`/`ProductResponse`, `ListingCreate`/`ListingUpdate`/`ListingResponse`, replacing `WatchItemCreate`/`WatchItemUpdate`/`WatchItemResponse`.
- **`backend/app/scheduler/jobs.py`** — `_process_item` rewritten to recompute the product's cheapest active listing and evaluate/alert at the product level; `Listing.last_scrape_status` set on every poll outcome (`ok`/`oos`/`error`), not just logged.
- **`backend/app/consumers/notify.py`** — `_format_price_drop` looks up `Product` instead of `WatchItem`; notification body names the winning retailer.
- **`backend/alembic/versions/000X_product_listing_split.py`** — new migration (Migration A only; Migration B is a separate future issue).
- **`.doc/database.md`, `.doc/api.md`** — schema/contract docs (database.md already updated this session; api.md needs the route table rewritten).
- **`backend/tests/api/test_items_routes.py`, `backend/tests/scheduler/test_jobs.py`, `backend/tests/consumers/test_notify.py`** — all need rewriting against the new model shape.

### Dependencies
- **`app/services/scraper/router.py`** (`RetailerRouter`, `detect_scraper_type`) — unchanged, still operates per-URL/per-listing; both new POST endpoints call it the same way `create_item` does today.
- **`app/models/price_history.py`** — unchanged, still FK's to `watch_items.id` (a listing), cascade-delete preserved.
- **Frontend `frontend/src/app/watchlist/page.tsx`** — not touched by this issue, but its mock `Product`/`Listing` shape is what the new `ProductResponse`/`ListingResponse` schemas are designed to match (#10.1 wires it up in a follow-on issue).

### Breaking Changes
- `GET /api/items` response shape changes completely (flat array → nested products). No API consumers exist yet in production (frontend still on mock data), so this breaks nothing live — but it does mean `.doc/api.md`'s documented contract is stale the moment this merges until it's updated.
- Existing `watch_items` rows are NOT deleted or renumbered — Migration A is additive/backfill only, per the two-phase expand/contract plan.
