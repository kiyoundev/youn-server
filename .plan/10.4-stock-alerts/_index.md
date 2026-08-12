# #10.4: Stock Alerts — Real Data + CRUD (Portfolio Tile + Market Detail Alarm)

> Re-scoped during planning. The original ticket text describes a new `/stocks`
> route with a full table — that route was never built and doesn't need to be.
> `/portfolio`'s Watchlist Tile and `/market/[ticker]`'s detail page already
> exist (shipped ahead of blockers, same pattern as #10.1/#36) and are the
> real target of this issue. See `context.md` for the full correction.

## PR / Branch
- **Branch:** `feature/10.4-stock-alerts`
- **PR Title:** `main | feature - 10.4 - Stock alert CRUD (portfolio tile + market detail alarm)`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
<!-- Rewritten from the ticket's stale ACs to match the agreed design — see context.md -->
- [ ] `/portfolio`'s Watchlist Tile displays real `StockAlert` rows from `GET /api/proxy/stocks` (no mock `stockWatchlistData`), auto-refreshing every 30s
- [ ] Paused alerts render at reduced opacity in the tile; the dead `+` button is removed
- [ ] `/market/[ticker]` shows a new alarm-icon button whose fill state reflects this ticker's alert(s): outline (none), filled (active), filled+muted (only paused), accent color (any triggered)
- [ ] Clicking the alarm icon opens a dialog with two independent sections — "Alert when price rises above" / "falls below" — each supporting create, edit target price, pause/resume, `run_analysis` toggle, and delete
- [ ] A create request for a direction that already exists for that ticker surfaces the backend's 409 as a toast, not a crash
- [ ] All mutations call `mutate("/api/proxy/stocks")` — tile and detail-page dialog reflect each other's changes without a page reload
- [ ] `X-API-Key` never appears in browser network tab (generic proxy, unchanged)
- [ ] `.doc/issues.md` #10.4 body/AC rewritten to match this design; #37 gets a one-line note that its target is two pages sharing one SWR key, not a `/stocks` route

## Estimated Effort
- Implementation: **~3.5 hours**
- Manual verification: **~0.5 hours** (frontend tests explicitly deferred to #29 — see `challenges.md`)
- **Total: ~4 hours** (revised up from the ticket's stale ~2h estimate)
