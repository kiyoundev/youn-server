# Issue #51: Manual Scrape Buttons (Per-Item + Global), Outside the 6h Schedule

## PR / Branch
- **Branch:** `feature/51-manual-scrape-buttons`
- **PR Title:** `main | feature - 51 - Manual scrape buttons (per-item + global)`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] Global button calls `POST /api/poll/prices`, surfaces the 429 cooldown message instead of a generic error, and results show up via the existing SSE refresh without a manual page reload
- [ ] New `POST /api/items/{product_id}/poll` route rescrapes only that product's own listings, reusing `_dispatch_first_scrapes` — not a second scraping implementation
- [ ] Manually-triggered re-scrape shows `"processing"` on the affected row/sheet via existing `compute_status()`, no changes needed to that function
- [ ] Rapid repeat clicks on the same product's button don't queue redundant concurrent scrapes of the same listings — rate-limit strategy decided and implemented, not left as a TODO
- [ ] Sheet-panel button disables while its own product's listings are in flight; re-enables once the SSE update lands
- [ ] No regression to `poll_prices`'s own 6h schedule or #41's add-time first-scrape — both still work unchanged

## Estimated Effort
- Implementation: **2 hours**
- Testing: **0.5 hours**
- **Total: 2.5 hours** (matches issue's own estimate)
