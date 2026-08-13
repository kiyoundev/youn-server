# #10.4: Stock Alerts — Real Data + CRUD (Market Detail Alarm)

> Re-scoped during planning. The original ticket text describes a new `/stocks`
> route with a full table — that route was never built and doesn't need to be.
> `/market/[ticker]`'s detail page already exists (shipped ahead of blockers,
> same pattern as #10.1/#36) and is the real target of this issue. See
> `context.md` for the full correction.
>
> **Second correction (2026-08-12, mid-implementation):** `/portfolio`'s
> Watchlist Tile was originally in this issue's scope too — pulled out into
> `#10.6` once it became clear the tile must never display `StockAlert` data
> (config, not market data) and that tile membership is actually the star
> icon's job, not alert existence. This issue is now alarm-icon + sheet only.

## PR / Branch
- **Branch:** `feature/10.4-stock-alerts`
- **PR Title:** `main | feature - 10.4 - Stock alert CRUD (market detail alarm)`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ✅ Done | [review.md](review.md) |

## Success Criteria
<!-- Rewritten from the ticket's stale ACs to match the agreed design — see context.md -->
<!-- Corrected 2026-08-12: the Watchlist Tile's own criteria moved to #10.6 — this
     issue never displays StockAlert data on /portfolio; see implementation.md's
     Step 2 note and #10.6's "Why" section for the full reasoning. -->
- [x] `/market/[ticker]` shows a new alarm-icon button whose fill state reflects this ticker's alert(s): outline (no alerts), filled (any alert exists, active or paused — simplified 2026-08-13, no muted/accent states)
- [x] Clicking the alarm icon opens a `Sheet` with two independent sections — "Alert when price rises above" / "falls below" — both always showing the same full field set (price, active, `run_analysis`) whether that alert exists yet or not
- [x] Field edits/toggles are draft-only — zero network requests until the sheet-level `Save` (revised 2026-08-13, supersedes the original immediate-commit-per-field design; see `implementation.md`'s Step 3 note for why); `Cancel` reverts all drafts, no request; `Save` batches each changed section into one request, both sections independently if both are dirty
- [x] Delete stays immediate and separate — its own confirm `Dialog` (same pattern as `watchlist/page.tsx`'s product sheet), not part of the Save/Cancel draft
- [x] A create request for a direction that already exists for that ticker surfaces the backend's 409 as a toast, not a crash
- [x] All mutations call `mutate("/api/proxy/stockalerts")` — the alarm sheet reflects its own changes without a page reload (no longer a claim about the `/portfolio` tile — see `#10.6`)
- [x] `X-API-Key` never appears in browser network tab (generic proxy, unchanged)
- [x] `.doc/issues.md` #10.4 body/AC status corrected; `#10.6` created as the Watchlist Tile's real owner; `#37`'s scope note already covers the alert-only SSE boundary independent of this split

## Estimated Effort
- Implementation: **~3.5 hours**
- Manual verification: **~0.5 hours** (frontend tests explicitly deferred to #29 — see `challenges.md`)
- **Total: ~4 hours** (revised up from the ticket's stale ~2h estimate)
