# Issue #24: Wishlist Product/Listing Model (Multi-Retailer Grouping)

## PR / Branch
- **Branch:** `feature/24-wishlist-product-listing-model`
- **PR Title:** `main | feature - 24 - Wishlist Product/Listing model`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
<!-- From issue acceptance criteria, refined during grill-me design session -->
- [x] Migration A creates `products` + `product_id` FK on `watch_items`, backfills every existing row as a product-of-one, preserves all existing data — applied to the real NAS DB (`0007 -> 0008 -> 0009`), verified via row counts and `information_schema` column check. `pg_dump` snapshot was skipped by user decision; turned out moot since `watch_items` was empty pre-migration (no real data existed to lose)
- [x] `GET /api/items` returns products with nested `listings[]`, each with a computed per-listing stock indicator (`last_scrape_status`)
- [x] `POST /api/items` creates a new product + its required first listing
- [x] `POST /api/items/{product_id}/listings` adds a new listing to an existing product
- [x] `PATCH /api/items/{product_id}` edits the product's shared name/target price
- [x] `PATCH /api/items/{product_id}/listings/{listing_id}` pauses/unpauses one listing; `DELETE` removes one listing, auto-deleting the product too if it was the last listing
- [x] Price-drop detection compares the cheapest *active* listing's price against `Product.target_price`, recomputed on every scrape (not just the listing that was just scraped)
- [x] Alert dedup/re-arm (`alerted_at`) lives on `Product`, fires once per crossing regardless of which listing triggered it
- [x] `status` (`watching`/`triggered`/`paused`/`failed`) computed server-side per the priority rules in [schema.md](schema.md), not duplicated in frontend logic
- [x] `last_scrape_status` (`ok`/`oos`/`error`) tracked per listing, surfaced independently of product `status`
- [x] Migration B (dropping the old `watch_items` columns) tracked as a separate follow-up issue, not required for this one to close

All application code written, full test suite (244 tests) passes, Migration A applied to and verified against the real NAS DB. Issue #24 is functionally complete — only [review.md](review.md) (code review pass) remains before closing it out.

## Estimated Effort
- Implementation: **7 hours**
- Testing: **2 hours**
- **Total: 9 hours**

(Original issue estimate was ~6h; grew during grill-me design session — `last_scrape_status` tracking and the split `POST` endpoints weren't in the original issue text. See [context.md](context.md) for what changed and why.)
