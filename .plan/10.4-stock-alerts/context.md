# #10.4: Context

## Issue Description

**Original ticket text** (`.doc/issues.md`, now stale — see "Correction" below):

> `/stocks` page — table of `StockAlert`s against the already-built backend
> (`stocks.py`'s CRUD routes). Columns: ticker, last price, target price,
> direction, `run_analysis` toggle, status badge, actions (edit, pause/resume,
> delete); add stock form. SWR polling, 30-second refresh.

**Original ACs:**
- `/stocks` displays all `StockAlert`s; `run_analysis` toggle updates via PATCH
- Add/edit/pause/delete actions all update the table without full page reload
- Table auto-refreshes every 30 seconds

### Correction to this issue's framing (found during planning, same class of gap #10.1 hit)

The ticket assumes a new `/stocks` route doesn't exist yet and needs building
from scratch, table-first, same shape as `watchlist/page.tsx`. Codebase
inspection during planning found that's wrong on two counts:

1. **There is no `/stocks` route, and there never was one meant to exist.**
   The nav item that would've been "Stocks" was named `/portfolio` instead —
   confirmed with the user, not a rename this issue needs to make.
2. **`/portfolio` already has a compact "Watchlist Tile"** (`app/portfolio/page.tsx:382-424`)
   rendering mock `stockWatchlistData` (`lib/mock-portfolio.ts`) — ticker,
   category badge, price, change%, whole-row `<Link>` to `/market/[ticker]`,
   a stub `+` button. Same "shipped ahead of blockers" situation #10.1 hit
   with `watchlist/page.tsx`.
3. **`/market/[ticker]` already has a star icon** (`app/market/[ticker]/page.tsx:136-144`)
   toggling local `watchlisted` state against the same mock array — this is
   a separate, unrelated concept (general bookmark, not `StockAlert`-backed)
   and stays untouched by this issue, confirmed with the user.

Design worked out with the user during planning: keep the tile's existing
visual shape (read-only, real data, no new mutation UI crammed into a
compact row); put all `StockAlert` mutation UI on `/market/[ticker]`
instead, behind a **new, separate alarm-icon button** (distinct from the
existing star) that opens a sheet (`Sheet`, `side="right"` — corrected
2026-08-12 from an originally-planned `Dialog`, see `implementation.md`'s
Step 3 note for why). See `schema.md` for the sheet's exact shape and
`challenges.md` for why it has two independent sections rather than one form.

## Component / Route Summary

### Current State

- **`frontend/src/app/portfolio/page.tsx:382-424`** — "Watchlist Tile" renders
  `stockWatchlistData` (mock, `lib/mock-portfolio.ts:51-55`): `{ ticker,
  category, targetPrice, direction, currentPrice }[]`. Whole row is a
  `<Link href="/market/[ticker]">`. Header has a stub `+` button
  (`aria-label="Add item"`, no handler).
- **`frontend/src/app/market/[ticker]/page.tsx:136-144`** — star icon toggles
  local `watchlisted` `useState`, seeded from `stockWatchlistData.some(...)`.
  No persistence, no backend call. **Out of scope, left as-is.**
- **`backend/app/api/stockalerts.py`** — full CRUD already built and tested
  (`backend/tests/api/test_stocks_routes.py`, `backend/tests/test_stocks.py`):
  `GET/POST /api/stockalerts`, `GET/PATCH/DELETE /api/stockalerts/{id}`, plus
  `POST /api/stockalerts/{id}/analyze` and `GET /api/stockalerts/{id}/analysis`
  (both out of scope here — see below).
- **`frontend/src/app/api/proxy/[...path]/route.ts`** — generic catch-all
  proxy already relays `/api/proxy/stockalerts/*` with no changes needed (same
  one `#36` built for `/api/proxy/items`).
- **`frontend/src/lib/api/items.ts`** — the pattern this issue's new
  `lib/api/stock-alerts.ts` mirrors: typed request/response interfaces, one
  function per mutation, a shared `ApiError` class, `request<T>()` helper.
- No frontend test infra exists at all (`frontend/package.json` has no
  Vitest/RTL/Jest dependency or config) — `#29` is the ticket that adds it.

### Target State

<!-- Corrected 2026-08-12 — the Watchlist Tile bullet below was removed, not
     updated: that work is entirely #10.6's now (tile reads /api/proxy/watchlist
     + /api/proxy/market/quotes, never StockAlert). This issue's target state
     is the detail-page sheet only. -->
- `/market/[ticker]` gains a new alarm-icon button in the header (next to
  the untouched star, which itself becomes real via `#10.6` rather than
  staying decorative) whose fill/color reflects this ticker's alert state,
  and a `Sheet` (opened by that icon, `side="right"` — same container
  `watchlist/page.tsx` uses for a product's detail panel, not a `Dialog`;
  see this file's earlier note) with two independent sections — above-alert
  and below-alert — each supporting create/edit/pause/`run_analysis`, and
  delete via a nested confirm `Dialog`.
- New `frontend/src/lib/api/stock-alerts.ts` — typed API client, same shape as
  `lib/api/items.ts`. Already built (`#10.4`'s Step 1).
- `mutate("/api/proxy/stockalerts")` after any mutation keeps the sheet's own
  state in sync without page reload — no SSE, no new proxy work. No longer a
  claim about `/portfolio`'s tile, which doesn't read this endpoint at all.

## Impact & Risk

### Files Changed
<!-- portfolio/page.tsx removed from this list 2026-08-12 — that file's
     Watchlist Tile work belongs to #10.6 now, not this issue. -->
- **`frontend/src/app/market/[ticker]/page.tsx`** — add alarm-icon button +
  two-section `Sheet`; wire to real alert data for this ticker (filtered
  client-side from the same SWR list, no per-ticker backend route exists).
- **`frontend/src/lib/api/stock-alerts.ts`** (new) — typed CRUD client.
- **`.doc/issues.md`** — rewrite #10.4's body/AC to match this design (see
  `_index.md`); add a one-line note to #37.

### Dependencies
- **`lib/toast.ts`** — reused as-is for mutation success/error feedback.
- **`components/ui/sheet.tsx`, `dialog.tsx` (delete-confirm only), `switch.tsx`,
  `input.tsx`, `button.tsx`** — reused as-is, same components `watchlist/page.tsx`
  already uses for its product detail panel + delete confirmation.
- **`lib/mock-portfolio.ts`** — `stockWatchlistData` and its
  `StockAlertData`/`StockAlertDirection` types become dead once the tile
  switches to real data; `holdingsData` (Position mock, `#19`'s concern)
  and `mockTickerDirectory` are untouched and still used elsewhere.

### Breaking Changes
None — no other page imports `stockWatchlistData`, and the backend/proxy
are unchanged. `#37` (blocked by this issue) needs a docs note since its
"swap `/stocks` polling for SSE" framing assumed a route that doesn't
exist — see `_index.md`'s success criteria.
