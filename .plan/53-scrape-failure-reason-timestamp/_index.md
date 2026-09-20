# Issue #53: Surface Scrape Failure Reason + Timestamp on the Item Sheet Panel

## PR / Branch
- **Branch:** `feature/53-scrape-failure-reason-timestamp`
- **PR Title:** `main | feature - 53 - Scrape failure reason + last-checked fix`
- **Note:** this repo doesn't actually use branches (solo project, direct commits to `main` — see `.doc/issues.md`'s own numbering being the real ticket system here). Branch/PR fields above are nominal, kept for consistency with this skill's template — commit directly to `main` as done all session, unless a branch is specifically wanted for this one.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & Data Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | 🟡 Built + unit-tested, awaiting deploy + live verification | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] `error_reason: str | None` added to `ScraperResult`, populated at every point a scraper returns `status="error"` — including `IKEAScraper`'s three error returns — via a `_describe_exception` helper so reasons are never empty or multi-line
- [ ] `_bounded_process_item`'s unexpected-exception backstop also persists a reason
- [ ] `status="ok"` + `price is None` transitions to `status="error"` with its own reason (resolved: was previously left ambiguous)
- [ ] The silent no-price-found path in `base.py`'s `_run_hierarchy` is no longer silent — content-based bot-block detection (Cloudflare "Just a moment", Akamai "Access Denied") gives a specific reason when detected, generic fallback otherwise
- [ ] Migration `0017` adds `last_scrape_error` and `last_checked_at` (both nullable) to `watch_items` — applied locally, not yet on the Pi/NAS
- [ ] `last_scrape_error` clears on the listing's next `"ok"` **or** `"oos"` scrape (not just `"ok"`)
- [ ] `last_checked_at` is set on **every poll attempt** — `ok`, `oos` and `error` alike; `_fetch_last_checked_map`/`compute_last_checked` derive from it instead of `PriceHistory.checked_at`
- [ ] Watchlist table row: hovering the "Failed" status badge shows a tooltip with each failed listing's reason (reason only)
- [ ] Sheet panel: header badge gets the same tooltip, and each listing row gets a `CircleAlert` icon (next to the external-link icon) when that specific listing is `"error"`, its tooltip showing that listing's reason — no separate "Error section"
- [ ] No migration backfill — existing listings' `last_checked_at` starts `null`, self-heals within one `poll_prices` cycle; legacy `"error"` listings show `"no details recorded yet"`
- [ ] Verified live against a real failure (a served fake Akamai deny page, or #52's Crate & Barrel case if it recurs)

## Estimated Effort
- Implementation: **3.5 hours**
- Testing: **1.5 hours** (includes updating ~10 existing full-equality error assertions)
- **Total: 5 hours**
