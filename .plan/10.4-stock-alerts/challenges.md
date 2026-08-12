# #10.4: Challenges & Notes

## Potential Challenges

1. **Two-section dialog, not a single form.** Because up to two alerts
   (above/below) can exist per ticker independently, a single create/edit
   form would have to silently pick one and hide the other's existence.
   Resolved with the user: the dialog always shows two sections — "Alert
   when price rises above" and "Alert when price falls below" — each
   independently: empty state (just a price input + "Add" if no alert
   exists for that direction) or populated state (price input, active/pause
   `Switch`, `run_analysis` `Switch`, delete button, if one does). Mitigates
   the ambiguity by not collapsing it in the first place, at the cost of a
   slightly busier dialog than a single-alert form would need.

2. **`last_price` is `null` until a Finnhub tick arrives.** Populated only
   by the WebSocket tick handler (`services/stocks.py`), not by `POST`. A
   freshly created alert, a market-closed session, or `FINNHUB_API_KEY`
   unset in this environment all show `last_price: null` indefinitely — not
   a bug, expected during manual verification. Null-guard the tile's
   change% math the same way `watchlist/page.tsx`'s `bestPrice()` does
   (fallback `"—"`, never `NaN`). Note separately: the alarm icon's
   "triggered" color keys off `alerted_at`, which is set by the same tick
   handler on threshold crossing — so a quiet Finnhub feed means the icon
   also never shows triggered, independent of whatever's shown for price.

3. **409 on create, reachable even with the two-section design.** The
   dialog only lets you add a direction that doesn't already show a
   populated section, but the SWR data backing that check can be up to 30s
   stale (or racing another tab's mutation) — a create could still hit the
   backend's real 409. Surface it as a toast (`ApiError.status === 409` →
   "An alert for this direction already exists"), then `mutate()` to pull
   the actual current state into view rather than leaving the dialog
   showing a stale "empty" section.

4. **Stale ticket text.** `.doc/issues.md`'s #10.4 body and ACs describe a
   `/stocks` table route that was never built and isn't being built here —
   see `context.md`'s "Correction" section. Rewriting that doc text is part
   of this issue's implementation, not a side note — otherwise the next
   person (or `#37`, which is directly blocked by this issue and currently
   says "`/stocks`/`/portfolio` page(s) swap `refreshInterval` polling for
   `EventSource`") plans against a route that doesn't exist.

## Key Differences

| Aspect | Ticket's original framing | Actual target (this plan) |
|--------|---------|--------|
| Route | New `/stocks` page, full sortable table | Existing `/portfolio` Watchlist Tile (compact, read-only) + existing `/market/[ticker]` (mutations) |
| Add/edit/pause/delete UI | Row actions + dropdown on the table | Two-section dialog behind a new alarm icon on `/market/[ticker]` |
| Status badge | Explicit status badge column | No status badge on the tile; paused rows dimmed instead; triggered state lives on the alarm icon's color, not the tile |
| `run_analysis` | Inline toggle in the table row | `Switch` inside the dialog's per-direction section |
| Nav | Implied a `/stocks` nav link | None needed — `#10.5`'s nav already covers the real route (`/portfolio`) |
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
2. Delete `frontend/src/lib/api/stocks.ts`.
3. Revert the `.doc/issues.md` doc correction if it's judged premature to
   keep (unlikely — it's a factual correction, not a design bet).
4. Verify: `/portfolio` and `/market/[ticker]` render without runtime
   errors against the restored mock data.
