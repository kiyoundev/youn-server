# #10.4: Challenges & Notes

## Potential Challenges

1. **Two-section sheet, not a single form.** Because up to two alerts
   (above/below) can exist per ticker independently, a single create/edit
   form would have to silently pick one and hide the other's existence.
   Resolved with the user: the sheet always shows two sections — "Alert
   when price rises above" and "Alert when price falls below" — each with
   the same full field set (price, active, `run_analysis`) whether that
   alert exists yet or not (revised 2026-08-13 — see item 4 below; no more
   fewer-fields-while-empty distinction), delete button shown only when a
   real alert exists. Mitigates the ambiguity by not collapsing it in the
   first place, at the cost of a slightly busier sheet than a single-alert
   form would need.
   <!-- Corrected 2026-08-12: container is a Sheet (side="right"), not a
        Dialog — ground-truthed against watchlist/page.tsx, whose Dialog
        usage is strictly create-only/confirm, never edit+toggle+delete;
        that combination only exists in its Sheet. Delete stays a nested
        confirm Dialog, same as that Sheet already does. -->

2. **`alerted_at`-driven "triggered" state can lag a quiet Finnhub feed.**
   The alarm icon's accent-color "triggered" state keys off `alerted_at`,
   set only by the WebSocket tick handler (`services/stocks.py`) on an
   actual threshold crossing — a freshly created alert, a market-closed
   session, or `FINNHUB_API_KEY` unset in this environment all leave it
   `null` indefinitely. Not a bug, expected during manual verification.
   <!-- Narrowed 2026-08-12: this item used to also cover the tile's
        change%/last_price null-guard — that's #10.6's concern now (its
        price data comes from /api/market/quotes, unrelated to last_price's
        known staleness, see .doc/issues.md's #19 "Correction" note for the
        full trace on why last_price specifically isn't a live price). -->

3. **409 on create, reachable even with the two-section design.** The
   sheet only lets you add a direction that doesn't already show a
   populated section, but the SWR data backing that check can be up to 30s
   stale (or racing another tab's mutation) — a create could still hit the
   backend's real 409. Surface it as a toast (`ApiError.status === 409` →
   "An alert for this direction already exists"), then `mutate()` to pull
   the actual current state into view rather than leaving the sheet
   showing a stale "empty" section.

4. **Draft session can outlive the data it was based on (added 2026-08-13).**
   Each `AlertSection`'s create-vs-edit branch on `Save` is decided by
   whether its `alert` prop is defined — sourced fresh from SWR's `alerts`
   data on every render, not snapshotted when the sheet opened. Since the
   sheet's `Save`/`Cancel` redesign (see `implementation.md`'s Step 3 note)
   means a draft can now sit open for as long as the user takes to fill in
   both sections, there's a real window (up to the 30s poll interval, or a
   background revalidation from another tab) where the underlying data
   changes *while* a draft is in progress — e.g. a section that was a
   create-candidate when the sheet opened could have a real alert appear
   underneath it before `Save` is clicked, flipping that section from
   create to edit without the draft's local state knowing. Not new in kind
   — same root cause as item 3's 409 race, just a longer window now that
   edits aren't committed instantly. `Save`'s create-vs-update check
   reading the *current* `alert` prop at click time (not a value captured
   at sheet-open) is what keeps this from actually corrupting anything —
   worst case is a 409 (if it flipped to "already exists" and the draft
   still tried to create) surfaced the same way item 3 already handles.

## Key Differences

<!-- Tile-related rows removed 2026-08-12 — #10.4 no longer touches the
     Watchlist Tile at all (see .doc/issues.md #10.4's own rewrite note and
     #10.6). Table below covers this issue's actual remaining scope only:
     the alarm sheet on /market/[ticker]. -->

| Aspect | Ticket's original framing | Actual target (this plan) |
|--------|---------|--------|
| Route | New `/stocks` page, full sortable table | Existing `/market/[ticker]` detail page (mutations only — no standalone route) |
| Add/edit/pause/delete UI | Row actions + dropdown on the table | Two-section `Sheet` behind a new alarm icon on `/market/[ticker]` |
| Status badge | Explicit status badge column | No status badge — triggered state lives on the alarm icon's color |
| `run_analysis` | Inline toggle in the table row | `Switch` inside the sheet's per-direction section |
| Nav | Implied a `/stocks` nav link | None needed — `#10.5`'s nav already covers `/portfolio` and `/watchlist` |
| Manual analyze trigger | Not mentioned, but backend route exists | Explicitly deferred to `#11` |
| Frontend tests | Not mentioned | Explicitly deferred to `#29` (no test infra exists yet — see below) |

## Testing note (not a rollback concern, but worth stating plainly)

No Vitest/RTL/Jest exists anywhere in `frontend/` — confirmed via
`package.json` and a repo-wide search during planning. `#29` ("Frontend Test
Suite — Vitest Setup + Watchlist Components + Proxy Route") is the ticket
that adds this infra; standing it up here would duplicate that ticket's
scope. Discussed with the user directly: skip frontend tests for this
issue, same call already made for `#10.2`. Manual verification only (see
`implementation.md` step 4).

## Rollback Plan
1. Revert `frontend/src/app/portfolio/page.tsx` and
   `frontend/src/app/market/[ticker]/page.tsx` to their pre-issue state
   (mock data restored) — `git revert` the merge commit, no DB/backend
   migration involved.
2. Delete `frontend/src/lib/api/stock-alerts.ts`.
3. Revert the `.doc/issues.md` doc correction if it's judged premature to
   keep (unlikely — it's a factual correction, not a design bet).
4. Verify: `/portfolio` and `/market/[ticker]` render without runtime
   errors against the restored mock data.
