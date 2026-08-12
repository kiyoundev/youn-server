# Issue #24: Challenges & Notes

## Potential Challenges

1. **First data-transforming migration in this repo, against a live NAS-hosted DB.** Every prior migration (`0001`-`0008`) only altered schema (add column, add constraint) — none moved or copied existing row data. Migration A's backfill step (`INSERT INTO products SELECT ... FROM watch_items`) is new territory. Mitigate with the `pg_dump` snapshot (implementation.md step 1) and a dry run against a local/dev DB copy before touching the NAS.

2. **Sequence collision if the backfill runs twice, or against a DB that already has `products` rows.** Reusing `watch_items.id` as `products.id` only works cleanly on a fresh backfill. If Migration A is ever re-run (e.g., after a failed partial apply), the `INSERT` would either fail on PK conflict (safe, loud failure) or double-insert if not idempotent. Write the migration to be safe to re-run: either wrap the backfill `INSERT` in `ON CONFLICT (id) DO NOTHING`, or check `SELECT COUNT(*) FROM products` is 0 before backfilling.

3. **`alerted_at` re-arm bug is easy to reintroduce if the scheduler rewrite is incomplete.** The whole point of recomputing `min(active listings)` on every scrape (not just comparing the just-scraped listing) is to avoid the bug walked through in [context.md](context.md) — an unrelated listing's routine poll incorrectly clearing `Product.alerted_at`. This is subtle enough that a partial/rushed rewrite could silently reintroduce it. The test case for this exact scenario (implementation.md step 10) should be treated as required, not optional.

4. **`RETAILER_MAP`/`detect_scraper_type` probe logic getting duplicated between the two POST endpoints.** Today it's inline in one `create_item` function; splitting into `POST /api/items` and `POST /api/items/{product_id}/listings` risks copy-pasting the branching logic (implementation.md step 6 calls for extracting a shared helper — don't skip this, it's the kind of duplication that silently drifts when one call site gets a bugfix and the other doesn't).

5. **`url` uniqueness is global, not scoped per-product — confirmed, no change needed.** Today's `unique=True` on `Listing.url` stays as-is: the same URL can never be added as a listing under two different products.

6. **Deleting a product's last listing auto-deletes the product — needs a frontend confirmation dialog.** Confirmed: `DELETE /api/items/{product_id}/listings/{listing_id}` on a product's last remaining listing cascades to delete the now-empty `Product` too (see [schema.md](schema.md)'s updated route description). Since this makes a listing-level delete capable of silently taking out the whole product, the frontend (#10.2, not this issue) must show a confirmation dialog before sending that specific delete request — the API itself performs the cascade unconditionally, it doesn't warn.

## Key Differences

| Aspect | Current | Target |
|--------|---------|--------|
| Model | Flat `WatchItem` (one row = one product at one retailer) | `Product` + `Listing` (one product, many listings) |
| `target_price`/`alerted_at` location | Per-listing | Per-product |
| Alert evaluation | Per-listing, in isolation | Per-product, recomputed across all active listings on every scrape |
| `GET /api/items` shape | Flat array | Nested array (products with `listings[]`) |
| `POST /api/items` | One endpoint, one purpose | Two endpoints (`POST /api/items` for new product, `POST /api/items/{id}/listings` for adding a retailer) |
| Stock availability | Not tracked | Per-listing `last_scrape_status` (`ok`/`oos`/`error`) |
| `status` badge | Not in current backend at all (frontend mock only) | Server-computed, 4 states, priority-ordered |
| Route IDs | Flat `{item_id}` | Nested `{product_id}` / `{product_id}/listings/{listing_id}` |

## Rollback Plan

1. Migration A's `downgrade()` drops the FK, drops `product_id`/`last_scrape_status` from `watch_items`, drops the `products` table entirely — since the original `watch_items` columns (`name`, `target_price`, `alerted_at`) were never touched or dropped in Migration A, this is a clean, lossless rollback of the schema change itself.
2. If rollback is needed *after* new products/listings have already been created through the new API (post-migration writes that only exist in `products`, not reflected back into `watch_items`'s old unused columns), those writes are lost on downgrade — this is expected and acceptable given Migration A is meant to be validated in a dev/local environment before ever touching the NAS-hosted production DB (implementation.md step 3).
3. If something looks wrong after Migration A runs against production, restore from the `pg_dump` snapshot taken in implementation.md step 1 rather than relying solely on the Alembic downgrade, since the snapshot is the more thoroughly-tested safety net for a first-of-its-kind data migration.
4. Application-code rollback (routes/scheduler/notify changes) is a normal git revert — no data implications, since none of that code touches the DB schema directly.
