# Issue #53: Surface Scrape Failure Reason + Timestamp on the Item Sheet Panel

## PR / Branch
- **Branch:** `feature/53-scrape-failure-reason-timestamp`
- **PR Title:** `main | feature - 53 - Scrape failure reason + timestamp`
- **Note:** this repo doesn't actually use branches (solo project, direct commits to `main` — see `.doc/issues.md`'s own numbering being the real ticket system here). Branch/PR fields above are nominal, kept for consistency with this skill's template — commit directly to `main` as done all session, unless a branch is specifically wanted for this one.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & Data Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] `error_reason: str | None` added to `ScraperResult`, populated at every point a scraper returns `status="error"`
- [ ] `status="ok"` + `price is None` now transitions to `status="error"` with its own reason (resolved: was previously left ambiguous)
- [ ] The silent no-price-found path in `base.py`'s `_run_hierarchy` is no longer silent — content-based bot-block detection (Cloudflare "Just a moment", Akamai "Access Denied") gives a specific reason when detected, generic fallback otherwise
- [ ] New Alembic migration (`0017`) adds `last_scrape_error`, `last_failed_at`, `last_checked_at` (all nullable) to `watch_items`
- [ ] `last_scrape_error`/`last_failed_at` clear on the listing's next `"ok"` **or** `"oos"` scrape (not just `"ok"`)
- [ ] `last_checked_at` set on `"ok"`/`"oos"`, not `"error"`; `_fetch_last_checked_map`/`compute_last_checked` derive from it instead of `PriceHistory.checked_at`
- [ ] Watchlist table row: hovering the "Failed" status badge shows a tooltip with each failed listing's reason
- [ ] Sheet panel: each listing row gets a `CircleAlert` icon (next to the existing external-link icon) when that specific listing is `"error"`, tooltip showing its own reason + relative last-failed time — no separate "Error section"
- [ ] No migration backfill — existing listings' `last_checked_at` starts `null`, self-heals within one `poll_prices` cycle
- [ ] Verified live against a real failure (re-triggering #52's Crate & Barrel Akamai case, if still reproducible)

## Estimated Effort
- Implementation: **3.5 hours**
- Testing: **1 hour**
- **Total: 4.5 hours**
