# #36: Wishlist Page (Real Data + Live Price History via SSE)

## PR / Branch
- **Branch:** `feature/36-wishlist-page-real-data-sse`
- **PR Title:** `main | feature - 36 - Wishlist page real data + live price history via SSE`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
<!-- Derived directly from .doc/issues.md #36 acceptance criteria -->
- [ ] `/watchlist` displays all real `Product`/`Listing` data from `GET /api/items` via the proxy — no mock data remains
- [ ] `X-API-Key` header never appears in browser network tab (proxy confirmed)
- [ ] A listing with `last_price: null` or `last_checked: null` renders a fallback (`—`), not `NaN`/`Invalid Date`
- [ ] Table sparkline shows the min price across a product's retailers, correctly merged by local day even when listings were scraped at different times within the same cycle
- [ ] Sheet chart shows one line per retailer, using the same underlying history data as the sparkline
- [ ] Backend emits an SSE push on every successful scrape, regardless of whether price changed
- [ ] Frontend reflects a scrape's result without a 30-second polling delay — no `refreshInterval` poll firing on this page
- [ ] An alert-crossing scrape still triggers Pushover/email exactly as before (existing `Event`/queue path unaffected)
- [ ] SSE connection recovers after a browser network drop, via manual reconnect logic, without a manual page refresh
- [ ] Reconnect attempts back off exponentially (1s → 2s → 4s → 8s...), not a fixed retry hammering every ~3s
- [ ] After a reconnect, the table reflects current truth immediately — sparkline lag for listings scraped mid-outage is acceptable, self-corrects on next scrape
- [ ] UI shows a distinct "offline" state (`navigator.onLine`) and a separate "live updates unavailable" state for any other sustained connection failure
- [ ] Manual test: rapid mount/unmount (React StrictMode) doesn't leak/duplicate backend connections

## Estimated Effort
- Implementation: **5 hours**
- Testing: **1 hour**
- **Total: 6 hours** (per `.doc/issues.md` — merges former `#10.1` ~2h + `#10.3` ~1.5h + ~2.5h net for SSE backend surface)
