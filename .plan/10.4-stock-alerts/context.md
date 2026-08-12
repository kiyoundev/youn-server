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
existing star) that opens a dialog. See `schema.md` for the dialog's exact
shape and `challenges.md` for why it has two independent sections rather
than one form.

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
- **`backend/app/api/stocks.py`** — full CRUD already built and tested
  (`backend/tests/api/test_stocks_routes.py`, `backend/tests/test_stocks.py`):
  `GET/POST /api/stocks`, `GET/PATCH/DELETE /api/stocks/{id}`, plus
  `POST /api/stocks/{id}/analyze` and `GET /api/stocks/{id}/analysis`
  (both out of scope here — see below).
- **`frontend/src/app/api/proxy/[...path]/route.ts`** — generic catch-all
  proxy already relays `/api/proxy/stocks/*` with no changes needed (same
  one `#36` built for `/api/proxy/items`).
- **`frontend/src/lib/api/items.ts`** — the pattern this issue's new
  `lib/api/stocks.ts` mirrors: typed request/response interfaces, one
  function per mutation, a shared `ApiError` class, `request<T>()` helper.
- No frontend test infra exists at all (`frontend/package.json` has no
  Vitest/RTL/Jest dependency or config) — `#29` is the ticket that adds it.

### Target State

- `/portfolio`'s Watchlist Tile fetches real `StockAlert[]` via
  `useSWR("/api/proxy/stocks", fetcher, { refreshInterval: 30_000 })`,
  same visual row shape, paused rows dimmed, `+` button removed.
- `/market/[ticker]` gains a new alarm-icon button in the header (next to
  the untouched star) whose fill/color reflects this ticker's alert state,
  and a dialog (opened by that icon) with two independent sections —
  above-alert and below-alert — each supporting create/edit/pause/delete/
  `run_analysis`.
- New `frontend/src/lib/api/stocks.ts` — typed API client, same shape as
  `lib/api/items.ts`.
- Both pages read the same SWR key (`/api/proxy/stocks`), so one
  `mutate("/api/proxy/stocks")` after any mutation keeps tile and dialog
  in sync without page reload — no SSE, no new proxy work.

## Impact & Risk

### Files Changed
- **`frontend/src/app/portfolio/page.tsx`** — replace mock `stockWatchlistData`
  usage in the Watchlist Tile with real SWR data; remove `+` button; dim
  paused rows; null-guard `last_price`.
- **`frontend/src/app/market/[ticker]/page.tsx`** — add alarm-icon button +
  two-section dialog; wire to real alert data for this ticker (filtered
  client-side from the same SWR list, no per-ticker backend route exists).
- **`frontend/src/lib/api/stocks.ts`** (new) — typed CRUD client.
- **`.doc/issues.md`** — rewrite #10.4's body/AC to match this design (see
  `_index.md`); add a one-line note to #37.

### Dependencies
- **`lib/toast.ts`** — reused as-is for mutation success/error feedback.
- **`components/ui/dialog.tsx`, `switch.tsx`, `input.tsx`, `button.tsx`** —
  reused as-is, same components `watchlist/page.tsx` already uses.
- **`lib/mock-portfolio.ts`** — `stockWatchlistData` and its
  `StockAlertData`/`StockAlertDirection` types become dead once the tile
  switches to real data; `holdingsData` (Position mock, `#19`'s concern)
  and `mockTickerDirectory` are untouched and still used elsewhere.

### Breaking Changes
None — no other page imports `stockWatchlistData`, and the backend/proxy
are unchanged. `#37` (blocked by this issue) needs a docs note since its
"swap `/stocks` polling for SSE" framing assumed a route that doesn't
exist — see `_index.md`'s success criteria.
