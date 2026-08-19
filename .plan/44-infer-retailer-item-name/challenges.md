# Issue #44: Challenges & Notes

## Potential Challenges

1. **`_derive_retailer` needs to move to avoid an import cycle.** It currently lives in `api/items.py`, which already imports `process_item`/`_dispatch_first_scrapes` from `scheduler/jobs.py`. Issue #44's `process_item` fill logic needs `_derive_retailer` too — importing it from `items.py` into `jobs.py` would create a cycle (`jobs.py` → `items.py` → `jobs.py`). Fix: move `_derive_retailer` (and its `_hostname_of` helper, if separate) into `services/scraper/router.py`, alongside `RETAILER_DISPLAY_NAMES` it already reads from — a more natural home than `items.py` anyway, and both `items.py` and `jobs.py` can import it from there without any cycle. Small mechanical move, same shape as `#48`'s own helper relocation (`_bounded_process_item`/`_dispatch_first_scrapes`, `items.py` → `jobs.py`) — do it the same way (cut, paste, update both import sites, verify with the full test suite).

2. **`<title>` heuristic is inherently guessable, not reliable.** Splitting on `–`/`—`/`|`/`-` to separate "product" from "site name" fails silently (returns `None`, which is fine) on titles with no separator, but can also produce a *plausible-looking but wrong* guess on titles that have a separator for an unrelated reason (e.g. `"Free Shipping - Today Only"` on a promo banner page misread as a product page). Low blast radius given the guards (retailer fill only touches untouched values; product name fill only touches `NULL` — a bad guess is user-correctable, not silently permanent), but worth being conservative: prefer returning `None` over a low-confidence guess when the title has ambiguous structure (e.g. more than one plausible separator, or a segment that's implausibly long/short for a name).

3. **`AmazonCAScraper._find_product_title` via `page.title()` may return a decorated title, not a clean product name.** Amazon product pages often format `<title>` as `"Product Name : Amazon.ca : Category"` or similar — a plain `page.title()` read isn't guaranteed to be exactly the product name without its own cleanup pass. Worth checking Amazon's actual title format live before assuming `page.title()` alone is good enough; may need the same separator-splitting heuristic as the generic path, applied to Amazon's own title string, rather than treating it as already-clean.

4. **No new race from `#48`'s concurrency — confirmed, not just assumed.** Two listings of the same product scraped concurrently (per `#48`) could both reach the `product.name` fill around the same time. Since this fill reuses `#48`'s existing `with_for_update()` locked read, the same row-lock serialization that prevents the double-alert race also serializes this — whichever listing's transaction gets there first fills `product.name` (if still `NULL`), commits, releases the lock; the second one's locked read then sees `product.name` already set and skips. No new guard needed, just confirm this reasoning holds when actually testing concurrent listings for a single product (same live-verification step `#48` already established a pattern for).

5. **Retailer-fill guard has a narrow false-positive window.** If a user manually sets `Listing.retailer` to a value that happens to exactly equal `_derive_retailer(hostname)` (e.g. they retype the same hostname-derived string themselves, or coincidentally choose the same value inference would have produced), a later scrape would treat it as "untouched" and silently overwrite it with the inferred value on the next successful scrape. Low-impact (the value was already equal, so the visible change is at most cosmetic — the user's choice happened to match the fallback), not worth a more complex guard (e.g. a dedicated boolean flag) for this edge case alone.

6. **Migration `downgrade()`'s `'Untitled'` backfill is an arbitrary placeholder**, same category of best-effort as `#48`'s `downgrade()` — any product left with `name IS NULL` (inference never completed, user never set one) gets a generic string before the `NOT NULL` constraint can be restored. Acceptable for a rollback path, not the forward migration.

## Key Differences

| Aspect | Current | Target |
|--------|---------|--------|
| `ScraperResult` | `price`, `status` only | + `site_name`, `product_title` (both optional, default `None`) |
| `_run_hierarchy` | Short-circuits on first successful price method; Shopify path never parses `soup` | Always parses `soup` once; name extraction runs independently of which price method won |
| `Listing.retailer` | Set once at creation (`_derive_retailer`), never touched again except by manual user edit | Also updated post-scrape if still untouched (guarded), same column, no schema change |
| `Product.name` | `NOT NULL`, always required at creation | Nullable; optional at creation, filled from `product_title` on first successful scrape if still `NULL` |
| `AmazonCAScraper` | Custom Playwright price extraction only | + its own title extraction, same guarded fill path as everything else |
| `ListingFailure` | `url`, `detail` | + `retailer` (hostname-derived, no scrape needed) |
| `_derive_retailer` location | `api/items.py` | `services/scraper/router.py` (moved to avoid an import cycle with `jobs.py`) |

## Rollback Plan
1. `git revert` the code commit(s) — no destructive schema change on the forward migration (purely additive nullable relaxation), so reverting code first is safe even before the DB migration is rolled back.
2. `alembic downgrade -1` if the migration needs reverting too — accept the best-effort `'Untitled'` backfill for any product left with a `NULL` name at that point.
3. Verify: existing products with names unaffected; retailer badges for already-created listings unaffected (guard means nothing retroactively changes for listings whose `retailer` no longer equals the deterministic fallback — i.e. once this feature has run once for a listing, reverting doesn't un-fill it).
