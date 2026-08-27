# Issue #51: Challenges & Notes

## Potential Challenges

1. **Zero-listing product hitting the new route** — resolved: `POST /api/items` allows `urls=[]` (product created with no listings, for callers that add listings separately), so this is reachable. Decided: no special-case in the route — `_dispatch_first_scrapes` on an empty `listing_ids` list is a no-op `gather()` that returns immediately, so it still 200s with `status="queued"` rather than needing its own branch or a 404.

2. **Per-product cooldown dict grows unbounded** — `_last_product_trigger: dict[int, datetime]` never evicts entries for deleted products. Low real-world risk (single-user app, product count stays small, each entry is one int key + one datetime), but worth a one-line note in the dict's docstring (matching `scrape_tracking.py`'s own "purely in-memory, process-local, restart loses it" framing) rather than silently leaving it unexplained.

3. **In-flight check granularity vs. `compute_status`** — the per-item button's `disabled` state should ideally reflect "this product's own listings are in flight," which `product.status === "processing"` already captures (per `compute_status()`'s existing logic) — but that same status also covers "never scraped since creation," a different reason to be `"processing"` that arguably shouldn't disable the button any differently (either way, nothing to click on that's meaningfully "in progress" yet vs. already running). Confirm this doesn't need splitting into a finer-grained flag before shipping — likely fine to reuse `status === "processing"` as the disable condition wholesale, called out here in case testing reveals otherwise.

4. **45s cooldown vs. real scrape duration** — if a real scrape (Patchright, cold browser start) sometimes takes longer than 45s, the in-flight check alone would still correctly block a repeat click during that window regardless of the cooldown timer's value, so the two guards aren't purely redundant — but a cooldown shorter than typical scrape time makes the cooldown branch nearly always be "shadowed" by the in-flight branch instead of ever firing in practice. Not a bug, just worth noting during manual testing which of the two rejection messages actually shows up.

## Key Differences

| Aspect | Current (global `poll_prices` trigger) | New (per-item trigger) |
|--------|------------------------------------------|-------------------------|
| Rate-limit scope | Process-wide, one `datetime \| None` | Per-product, `dict[int, datetime]` |
| Rate-limit window | 5 minutes | 45 seconds |
| Extra guard | None | `in_flight_snapshot()` overlap check |
| Scrape pool | `_poll_concurrency_semaphore` (jobs.py) | `_first_scrape_semaphore` (items.py, shared with #41) |

## Rollback Plan
1. Revert the single commit/PR — the change is additive (one new route, two new frontend functions, two new buttons), so reverting removes it cleanly with no data migration or cleanup needed.
2. Verify `poll_prices`'s 6h schedule and #41's add-time first-scrape still function (they were never modified, but confirm post-revert as a sanity check).
