# #10.4: Implementation

## Steps

### 1. Data Layer
- [x] Create `frontend/src/lib/api/stocks.ts` — `StockAlert`, `StockAlertCreatePayload`,
      `StockAlertUpdatePayload` (optional-only, no TradingAgents fields — see
      `schema.md`'s footgun note), `ApiError`, `createStockAlert()`,
      `updateStockAlert()`, `deleteStockAlert()`. Copy `lib/api/items.ts`'s
      `request<T>()` helper and `BASE` pattern, pointed at `/api/proxy/stocks`.

### 2. `/portfolio` Watchlist Tile — real data, read-only
- [ ] Add `useSWR<StockAlert[]>("/api/proxy/stocks", fetcher, { refreshInterval: 30_000 })`
      to `PortfolioPage`, reusing the same inline `fetcher` pattern
      `watchlist/page.tsx` uses (`(url) => fetch(url).then(r => r.json())`).
- [ ] Replace the `stockWatchlistData.map(...)` block (page.tsx:391-422) with
      the real list. Row key becomes `alert.id` (not `alert.ticker` — two
      alerts can now share a ticker, above + below).
- [ ] Null-guard change% math: `alert.last_price === null` → render `"—"`
      instead of computing `changePercent`/`changeDollar`.
- [ ] Paused alerts (`alert.active === false`) render the row at reduced
      opacity (e.g. `opacity-50` on the row's wrapper).
- [ ] Keep the category `Badge` — user confirmed keep-as-is even without a
      backend-sourced category field (hardcode `"Stock"`, matches current
      mock behavior for every ticker in practice today).
- [ ] Remove the header's `+` button (`<button aria-label="Add item">`,
      page.tsx:386-388) — dead stub, no longer has a natural target now that
      create lives on `/market/[ticker]`.
- [ ] Remove now-dead `stockWatchlistData`/`StockAlertData`/`StockAlertDirection`
      exports from `lib/mock-portfolio.ts` once nothing imports them — check
      `market/[ticker]/page.tsx`'s star-icon seed (`stockWatchlistData.some(...)`)
      first, since that stays and still needs *a* mock source; either leave a
      trimmed mock array just for the star, or seed it `false`-only (star is
      out of scope, functionally cosmetic either way — pick whichever is a
      smaller diff when you're in the file).
- [ ] Add loading/error states for the fetch (mock data could never fail) —
      match `watchlist/page.tsx`'s `isLoading`/`error` branches, scoped to
      just this tile rather than the whole page (the Holdings tile and chart
      sections still render fine off mock data independent of this fetch).

### 3. `/market/[ticker]` — alarm icon + two-section dialog
- [ ] Add `useSWR<StockAlert[]>("/api/proxy/stocks", fetcher, { refreshInterval: 30_000 })`
      to `MarketDetailPage` — same SWR key as the tile, dedup'd by SWR's
      cache automatically (no duplicate network request when both are
      mounted, e.g. tile → click-through → detail page).
- [ ] Derive `const alertsForTicker = data?.filter(a => a.ticker === ticker) ?? []`
      and `const aboveAlert = alertsForTicker.find(a => a.direction === "above")`,
      same for `belowAlert`.
- [ ] Add a new icon button next to the existing star (page.tsx:136-144),
      e.g. `AlarmClock` or `Bell` from `lucide-react` (match the star's
      `size-4`/`hover:bg-muted` treatment). Fill/color logic:
      - No alerts for this ticker → outline only
      - At least one active, none paused-only → filled
      - Only paused alert(s), none active → filled + muted (`opacity-50`,
        same treatment as the tile's paused rows)
      - Any alert with `alerted_at !== null` → filled + accent color
        (`var(--status-success)` or similar, overrides the muted case)
- [ ] Icon click opens a `Dialog` (same component `watchlist/page.tsx` uses
      for its Add Item dialog). Two sections, each independently:
      - **Empty** (no alert for that direction): price `Input` +
        "Add alert" `Button` → `createStockAlert({ ticker, target_price, direction })`
      - **Populated**: price `Input` (inline edit, same Enter-to-save pattern
        as watchlist's sheet fields), active/pause `Switch` (`checked={alert.active}`),
        `run_analysis` `Switch`, delete icon `Button`
      - All three mutation paths call `mutate("/api/proxy/stocks")` on
        success, `toast.success`/`toast.error` on result, same pattern as
        every mutation in `watchlist/page.tsx`.
      - 409 on create → `toast.error("An alert for this direction already exists")`
        specifically (branch on `err instanceof ApiError && err.status === 409`),
        not the generic fallback message.

### 4. Manual Verification
<!-- Frontend tests explicitly deferred to #29 — see challenges.md -->
- [ ] `/portfolio` Watchlist Tile shows real alerts, refreshes every 30s
      (network tab), paused alerts visibly dimmed, no `+` button
- [ ] Create an "above" alert from `/market/AAPL`'s dialog → row appears in
      `/portfolio`'s tile without reload; icon fills
- [ ] Create a "below" alert on the same ticker → both sections populated
      independently, tile shows 2 rows for `AAPL`
- [ ] Attempt to create a second "above" alert on the same ticker (e.g. via
      two tabs racing) → 409 toast, dialog doesn't silently duplicate
- [ ] Edit target price inline in the dialog → tile row updates without
      reload
- [ ] Toggle `run_analysis` in the dialog → `PATCH` fires, no other fields
      change (verify via network tab payload — should be exactly
      `{ run_analysis: true }`, not a wider object)
- [ ] Pause an alert → tile row dims, icon shows muted-filled state (if
      that was the only active alert for this ticker)
- [ ] Delete an alert → disappears from tile and dialog without reload
- [ ] `last_price: null` (no Finnhub tick yet) renders `"—"` in the tile,
      not `NaN`/blank
- [ ] `X-API-Key` never appears in Network tab for any `/api/proxy/stocks*`
      request

### 5. Cleanup
- [ ] Remove unused code — confirm no other file still imports
      `stockWatchlistData`/`StockAlertData` before deleting them from
      `lib/mock-portfolio.ts`
- [ ] Run `npm run lint` and fix errors
- [ ] Rewrite `.doc/issues.md`'s #10.4 body + ACs to match this design
      (see `_index.md`'s Success Criteria for the replacement text), update
      its estimate, and add a one-line note to `#37` clarifying its target
      is two pages sharing one SWR key rather than a `/stocks` route
