# #10.4: Implementation

## Steps

### 1. Data Layer
- [x] Create `frontend/src/lib/api/stock-alerts.ts` — `StockAlert`, `StockAlertCreatePayload`, `StockAlertUpdatePayload` (optional-only, no TradingAgents fields — see `schema.md`'s footgun note), `ApiError`, `createStockAlert()`, `updateStockAlert()`, `deleteStockAlert()`. Copy `lib/api/items.ts`'s `request<T>()` helper and `BASE` pattern, pointed at `/api/proxy/stockalerts`.

### 2. `/portfolio` Watchlist Tile — MOVED to `#10.6` (2026-08-12)

**Superseded, not part of this issue anymore.** Originally scoped here as "swap `stockWatchlistData.map(...)` for real `StockAlert` rows" — wrong premise, caught mid-implementation: the tile must never display anything from the `StockAlert` response (config data, not market data), and "which tickers appear in the tile" turns out to be the star icon's job (`market/[ticker]/page.tsx:75,138-143`, previously decorative/unpersisted), not alert existence. Full reasoning: `#10.6`'s "Why" section.

Everything below moved to `#10.6`, not duplicated here:
- The tile's `useSWR` fetch (now against `/api/proxy/watchlist` + `/api/proxy/market/quotes`, not `/api/proxy/stockalerts`)
- Replacing `stockWatchlistData.map(...)` with the real list
- The category `Badge` (`"Stock"`, unchanged) and paused-row dimming (now means "un-starred," not "alert paused")
- The header's dead `+` button removal
- Removing `stockWatchlistData`/`StockAlertData`/`StockAlertDirection` from `lib/mock-portfolio.ts` — same caveat about the star icon's mock seed still applies, now resolved by `#10.6` making the star real instead of leaving it mocked
- Loading/error states for the tile's fetch

This issue (`#10.4`) no longer has any Watchlist-tile responsibility — its remaining scope is Step 3 (`/market/[ticker]`'s alarm icon + sheet) only, which is unaffected by this correction.

### 3. `/market/[ticker]` — alarm icon + two-section sheet
<!-- Corrected 2026-08-12: container changed from Dialog to Sheet. Ground-truthed
     against watchlist/page.tsx — inline-editable fields (pencil → edit → Enter-to-save)
     and the pause/resume Switch only exist inside that page's product Sheet (206-468);
     its Dialog usage (470-485, 726-758) is strictly create-only or yes/no confirm, never
     edit/toggle/delete. This surface needs inline edit + 2 Switches + delete per section
     — Sheet's job, not Dialog's. Delete stays a nested Dialog for confirmation only,
     same as watchlist's product Sheet already does (470-485) — not a new pattern. -->
- [x] Add `useSWR<StockAlert[]>("/api/proxy/stockalerts", fetcher, { refreshInterval: 30_000 })` to `MarketDetailPage` — same SWR key as the tile, dedup'd by SWR's cache automatically (no duplicate network request when both are mounted, e.g. tile → click-through → detail page).
- [x] Derive `const alertsForTicker = data?.filter(a => a.ticker === ticker) ?? []` and `const aboveAlert = alertsForTicker.find(a => a.direction === "above")`, same for `belowAlert`.
- [x] Add a new icon button next to the existing star (`page.tsx:151-157` — already stubbed as `AlarmClockPlus` toggling decorative local `alertEnabled`; replace with the real thing below), matching the star's `size-4`/`hover:bg-muted`/`opacity-50` treatment exactly. Fill logic simplified 2026-08-13 (dropped the muted/accent states originally speced — not needed): binary only — `hasAlerts = alertsForTicker.length > 0`, filled (`fill-foreground opacity-100`) if true, outline (`opacity-50`) if false. No separate treatment for paused-only or triggered alerts.
- [x] `onClick` is a **constant** action — `() => setSheetOpen(true)`, always, regardless of `hasAlerts` — not a toggle of the same state driving the fill (unlike the star icon right next to it, whose `onClick` *does* toggle its own display state — different interaction shape, don't copy that part of the star's pattern here).
- [x] Icon click opens a `Sheet` (`side="right"`, same component + `SheetContent`/`SheetHeader`/`SheetTitle` `watchlist/page.tsx` uses for its product detail panel).

**Design, revised 2026-08-13 — draft-until-Save, not immediate-commit-per-field.**
Superseded the original design (each field's edit/toggle firing its own `PATCH` immediately, mirroring `watchlist/page.tsx`'s per-field Enter-to-save/instant-`Switch` pattern) — caught as a real flaw once built: editing price + toggling `active` + toggling `run_analysis` on one alert fired 3 separate requests and 3 full-list `mutate()` refetches for what's conceptually one edit. `watchlist`'s immediate-commit pattern fit *its* content (a handful of unrelated single-field toggles across many rows); it didn't fit this surface (up to 6 co-located fields across 2 sections of the same sheet). Confirmed with the user: nothing hits the network until a single `Save` click, not before.

- Both sections (above/below) always render the **same full field set** — Target Price `Input`, `active` `Switch`, `run_analysis` `Switch` — whether that alert exists yet or not. No more "fewer fields while creating, more after" (the earlier two-step create→edit asymmetry this design replaces).
- Every field edit only updates **local draft state** (per section: `{target_price, active, run_analysis}`, seeded from the real alert on mount/reset, or empty/`active: true` defaults for a not-yet-existing section) — no `updateStockAlert`/`createStockAlert` call, no `mutate()`, on any individual field change.
- **One `Save`/`Cancel` pair in a `SheetFooter`, covering both sections** — not per-section, not per-field. Above/below stay independent resources under the hood (still separate `create`/`update` calls if both changed), but the user only ever sees one button pair for the whole sheet; nothing fires before it's clicked.
  - `Save`: diff each section's draft against its real state — unchanged → skip; changed-and-existing → one `updateStockAlert(alert.id, {...only the changed fields})`; changed-and-new (price filled in) → one `createStockAlert({ticker, target_price, direction, active: true, run_analysis})`. Fire whichever apply (`Promise.allSettled`, not sequential — one section's failure shouldn't block the other's success), single loading state, then one `mutate("/api/proxy/stockalerts")`, then `toast.success`/`toast.error` summarizing the result (or per-section errors if only one failed).
  - `Cancel`: reset both sections' drafts back to server truth (or clear an empty section's draft), no request.
  - 409 on a section's create → that section's own error, not a blanket failure — `toast.error("An alert for this direction already exists")` specifically (branch on `err instanceof ApiError && err.status === 409`), the other section's Save (if it also had changes) still applies independently.
- **Delete stays exactly as originally designed — immediate, its own confirm, outside the draft entirely.** Delete icon `Button` → nested confirm `Dialog` ("Delete this alert?", same shape as `watchlist/page.tsx:470-485`) → `deleteStockAlert()` fires the instant it's confirmed, `mutate()`, `toast`. Not draftable/undoable via `Cancel` — a destructive action shouldn't be something a stray `Cancel` click silently reverts, and shouldn't wait behind unrelated field edits either.

### 4. Manual Verification
<!-- Frontend tests explicitly deferred to #29 — see challenges.md -->
<!-- Tile-visibility items moved to #10.6 (2026-08-12) — creating/editing/deleting an
     alert here no longer has any effect on the /portfolio tile, since the tile reads
     starred tickers + market data, not StockAlert rows. Only the alarm icon and sheet
     (this issue's own UI) are verified below. -->
- [x] Filling in a section's price / toggling its switches produces **zero** network requests (verify via network tab) until `Save` is clicked
- [x] Fill in "above" section's price, click `Save` → one `createStockAlert` request, alert appears, icon fills
- [ ] Fill in "below" on the same ticker in the same sitting (both sections dirty at once), click `Save` → both requests fire (`Promise.allSettled`), both sections populated
- [ ] Attempt to create a second "above" alert on the same ticker (e.g. via two tabs racing) → 409 toast scoped to that section only; a simultaneously-dirty "below" section still saves successfully
- [ ] Edit target price + toggle `run_analysis` in the same section in one sitting, click `Save` → exactly **one** `PATCH` request carrying both changed fields, not two separate requests
- [ ] Click `Cancel` after making changes → all fields revert to server state, zero requests sent
- [ ] Pause an alert (toggle `active` off, `Save`) → icon stays filled (any alert existing keeps it filled, active or paused — no separate muted state); icon only reverts to outline once every alert for that ticker is deleted
- [ ] Delete an alert → confirm dialog appears immediately (not gated behind `Save`), confirming removes it from the sheet without reload, independent of whatever unsaved draft state exists in either section
- [ ] `X-API-Key` never appears in Network tab for any `/api/proxy/stockalerts*` request

### 5. Cleanup
- [x] Run `npm run lint` and fix errors (this issue's own files only — `stockWatchlistData`/`StockAlertData` removal from `lib/mock-portfolio.ts` is `#10.6`'s cleanup now, since that's the issue that stops needing them) — verified 2026-08-13, `market/[ticker]/page.tsx` clean; the 3 remaining errors are pre-existing, in `portfolio/page.tsx`, unrelated to this file
- [x] `.doc/issues.md`'s #10.4 body/AC status — done 2026-08-12, see `#10.6`'s split-out and this file's Step 2 correction note
- [x] `#37` one-line note re: two pages sharing one SWR key rather than a `/stocks` route — superseded by `#10.6`'s split; `#37`'s own scope note (`.doc/issues.md`) already covers the alert-only SSE boundary independent of this
