# Frontend

Consolidated reference for what's on each dashboard page — cross-cuts issues #10.1–#10.5, #11, #19, #20, #21, #22, #23. Individual issues remain the source of truth for acceptance criteria; this doc exists so page/component scope doesn't have to be reconstructed from the issue backlog each time.

## Pages

| Route | Issue(s) | Purpose |
|---|---|---|
| `/` | #22 | Overview — bentobox summary across app data + host infra |
| `/wishlist` | #10.1, #10.2, #10.3 | `WatchItem` table (retail price-drop tracking) |
| `/stocks` | #10.4 | `StockAlert` table (stock threshold alerts) |
| `/stocks/{id}/analysis` | #11 | `AnalysisResult` list + TradingAgents version panel |
| `/portfolio` | #19, #23 | Holdings table, summary card, per-position history chart |

## Components by page

### `/` (Overview, #22)

8 tiles, final naming per mockup:

| Tile | Component | Data | shadcn components | Notes |
|---|---|---|---|---|
| System | `SystemTile` | CPU %, memory %, disk % (Pi's own disk), Pi temp — #21 `GET /api/system/resources` | `Progress` bar per metric, `Badge` for temp (color-threshold green/yellow/red) | Real-time snapshot, no historical trend — 3–4 progress bars is enough. Considered a circular/radial gauge (shadcn's recharts-based radial chart) instead of linear `Progress` — decided against it, keeping linear for simplicity |
| Notification | `NotificationTile` | TradingAgents + youn-server: current commit, update-available, commits-behind — #11's `GET /api/analysis/tradingagents/version` + #20's `GET /api/system/version` | `Badge` per repo (green "up to date" / yellow "N behind") | No action button here — click-through to #11's/#20's own panel for the actual "Update" trigger + git output. Keeps the home tile a glance, not a control surface |
| Storage | `StorageTile` | NAS per-volume used/total, per-disk SMART health — Synology DSM Web API (`SYNO.Core.Storage`), backend-cached via its own APScheduler interval job, not fetched live per page-load/poll | Dot-grid/waffle usage visual (custom — plain `div` grid + Tailwind, **not a native shadcn component**) for volume %, `Badge` list underneath for per-disk health (Healthy/Warning/Failed) | The only tile where a TB-scale usage widget makes sense. Backend not yet a formal issue — needs a NAS monitoring-account credential (limited permission, not admin) and a TLS decision for DSM's self-signed cert |
| Docker | `DockerTile` | Container name, status, image, uptime — #21's `GET /api/system/docker` | Compact list: name + status `Badge` (green running / red exited / yellow restarting); image/uptime shown in a `Tooltip` on hover, not always-visible columns | Keeps it glanceable — a full table crammed into a tile isn't the goal here |
| Portfolio | `PortfolioTile` | Ticker + shares per position — #19's `GET /api/positions` | Small headline stat (e.g. total gain/loss) + compact 2-column list (ticker, shares) | Name+count only — full detail lives on `/portfolio`'s `HoldingsTable`, not duplicated here |
| Watchlist | `WatchlistTile` | Name-only list/count of active `WatchItem`s — #10.1's `GET /api/items` | Plain list of names, reuse the existing 3-state `StatusBadge` (above/at/below target) per item | No TB-style usage widget — the mockup showed one here, but that's a placeholder carried over visually from the Storage tile, not semantically meaningful for wishlist items |
| Services | `ServicesTile` | Finnhub WS connected, dispatcher task alive/crashed, event-queue backlog — #21's `GET /api/system/services` | `Badge` (green Connected / red Disconnected) for WS, `Badge` (green Running / red Crashed) for dispatcher, plain stat number for backlog (shifts color if > 0) | 3 short status lines, no chart needed |
| Schedules | `SchedulesTile` | Per-job next-run-time + last-run outcome — #21's `GET /api/system/schedules` | Small `Table`: Job / Last Run (`Badge` success/error) / Next Run (relative time text) | Same mockup-artifact note as Watchlist — no TB widget. Scales naturally as more jobs (e.g. the Storage tile's NAS-poll job) get added, same shape, more rows |

Layout: CSS Grid (Tailwind `grid`/`col-span-*`/`row-span-*`) for the bentobox asymmetry, shadcn `Card` for each tile's chrome. Bentobox is a layout pattern, not a library feature — nothing shadcn-specific about the grid itself.

### `/wishlist` (#10.1, #10.2, #10.3)

| Component | Notes |
|---|---|
| `WatchItemTable` | name, retailer, current price, target price, status badge, last checked, actions (edit target, pause/resume, delete) — read: #10.1, actions: #10.2 |
| `AddWatchItemForm` | URL + name + target price — #10.2 |
| `PriceHistoryChart` | recharts `LineChart`, expands on row click, fixed 30-day window (`GET /api/items/{id}/history?days=30`) — #10.3 |

### `/stocks` (#10.4)

| Component | Notes |
|---|---|
| `StockAlertTable` | ticker, last price, target price, direction, `run_analysis` toggle, status badge, actions |
| `AddStockForm` | new alert |

Links to `/stocks/{id}/analysis` per row.

### `/stocks/{id}/analysis` (#11)

| Component | Notes |
|---|---|
| `AnalysisResultList` | one row per past `AnalysisResult`, 4-state status badge |
| `ResultJsonViewer` | collapsible, shown when `status="done"` |
| `RunAnalysisButton` | disabled + 409 message when already running |
| `TradingAgentsVersionPanel` | commit hash, "N commits behind" badge, update button, "not installed" state |

### `/portfolio` (#19, #23, #30, #31)

| Component | Notes |
|---|---|
| `HoldingsTable` | ticker, shares, avg cost, current price, market value, unrealized gain ($ and %), color-coded. Each row links to `/market/{ticker}` (#31) |
| `PortfolioSummaryCard` | total portfolio value, total invested, total gain/loss |
| `AddEditPositionForm` | shares/avg_cost/notes |
| `StockHistoryChart` | recharts `LineChart`, preset buttons (`1M`/`1Y`/`3Y`/`ALL`), per-position row expand — **separate component from `PriceHistoryChart`**, different data source (yfinance vs. scraped `PriceHistory`) and different controls (presets vs. fixed window); not worth a shared abstraction |
| `TrendingAssetsPanel` | segmented control (Stocks / ETFs / Indices), top 10 rows per category (indices: fixed curated list, not ranked) — ticker, name, price, % change, news-link icon. "View Details" per row links to `/market/{ticker}` (#31) |
| Stock watchlist list | ticker, current price, % change vs. target price (target price is the % baseline — no shares/avg-cost, since these aren't owned). Each row links to `/market/{ticker}` (#31) |

### `/market/[ticker]` (#31)

Ticker-scoped detail page, reachable from `HoldingsTable` rows, the stock watchlist list, and `TrendingAssetsPanel`'s "View Details" — reusable for any ticker regardless of whether it also has a `Position` or `StockAlert` row (same reusability reasoning as #23's `GET /api/market/{ticker}/history`). Layout confirmed against a real Wealthsimple reference screenshot (SOFI, 2026-07-29) — field list and conditional sections below are read directly off that reference, not guessed.

**Always shown, any ticker:**

| Component | Notes |
|---|---|
| `MarketDetailHeader` | logo, ticker, company name |
| `MarketDetailChart` | recharts `LineChart`, preset buttons `1D`/`1W`/`1M`/`3M`/`6M`/`YTD`/`1Y`/`10Y`, "Markets closed" status indicator — **separate component from `StockHistoryChart`**, different context (dedicated page vs. inline holdings-row expand) and different range needs |
| `MarketDetailsPanel` | Open; Bid **+ quote size** (`$16.14 x 1`); Ask **+ quote size** (`$16.21 x 101`); Last sale (price only, no trade size — see gap below); High; Low; Volume; Average volume; 52-week high; 52-week low; Exchange — all sourced from yfinance `Ticker.info` (none of this is on Finnhub's free tier). Bid/ask fields exist on yfinance but are known to be flaky/stale on the free unofficial API, more so outside market hours — kept anyway since there's no better free source, but don't treat as always-reliable |
| `FinancialsPanel` | Market cap, Shares outstanding, P/E ratio |
| `AboutPanel` | company description (yfinance `longBusinessSummary`), shown in full — no truncation/"Show more" |

Margin requirement is technically shown in the Wealthsimple reference, but stays **dropped** per #31's existing scope note — brokerage house rule, not applicable to a read-only tracker, no field for it on Finnhub/yfinance regardless.

Last-sale trade size (the "x 5,000" part) is also **dropped** — checked both providers: yfinance's `Ticker.info` has no last-trade-size field, and Finnhub's free-tier `/quote` REST endpoint returns price/high/low/open/previous-close only (no bid/ask/size at all — that sits behind Finnhub's paid plan). The only place either provider exposes trade size on the free tier is Finnhub's WebSocket trade stream (already used for `StockAlert` price ticks, #4), which is a live print feed you'd have to keep connected and cache from — a much bigger lift than the rest of this panel, not worth it for one field.

**Conditional — only when the ticker has dividend data** (`dividendYield`/`dividendRate` not null on yfinance's `Ticker.info`):

| Component | Notes |
|---|---|
| `DividendsPanel` | Frequency, 12-month yield, Ex-dividend date, Expected payment date |

The SOFI reference screenshot has no Dividends section at all — SOFI pays no dividend, so Wealthsimple's own UI omits the panel rather than showing empty fields. Same behavior here, not a dropped feature.

**Conditional — only when a `Position` exists for the ticker (shares > 0):**

| Component | Notes |
|---|---|
| Chart reference-price overlay | Dashed horizontal line at the price of the **most recent buy tranche** for this ticker (not the position's weighted `avg_cost` — if there were multiple buys at different prices, the line tracks the latest one, sourced from `Activity` rows via #33, falling back to `avg_cost` only if no matching `Activity` exists), vertical marker + dot at that tranche's date, floating $ label on the line — layered onto `MarketDetailChart`, not a separate component |
| `PositionSummaryCard` | "Stocks" header + `1D`/`All` toggle; columns: share count, currency, allocation % (portfolio weight, with info icon), qty, current price, total value, all-time return ($ and %, `(current − avg_cost) × shares`) |

**Conditional — independent check: only when `Activity` rows (#33) exist for the ticker** (a fully-sold position has no current `Position` row but should still show its trade history):

| Component | Notes |
|---|---|
| `RecentActivityPanel` | Date-grouped list of `RecentActivityCard` rows |
| `RecentActivityCard` | Collapsed: icon, ticker, order-type label + account tag (e.g. "Limit buy · TFSA"), amount + settlement currency, expand chevron. Expanded (see field mapping and gaps below): Account, Status, Submitted, Filled, Trading session, divider, Type, Limit price, Entered quantity, Filled quantity, Exchange rate, divider, Total cost |

`RecentActivityCard` field → `Activity` (#33) mapping, and what the confirmed CSV shape can't currently supply:

| Card field | Source | Gap |
|---|---|---|
| Account | `account_type` | none |
| Status | — | CSV has no status field; render hardcoded "Completed" (activity exports only contain settled transactions) |
| Submitted | `transaction_date` | date only, no time-of-day in CSV — omit the time line or show date only |
| Filled | `settlement_date` | same — date only |
| Trading session | — | not derivable from CSV, omit |
| Type | `activity_sub_type` | CSV sample so far only shows `BUY`; expected real values per user: `MARKET_BUY`, `LIMIT_BUY`, `STOP_LIMIT_BUY`, `STOP_MARKET_BUY`, `RECURRING_BUY` (unconfirmed literal enum strings — validate against a real export once one containing a non-market order is available) |
| Limit price | — | CSV's `unit_price` is the **execution** price, not the order's original limit price — these differ (reference shows limit $18.30 vs. filled $18.29). Not capturable from this CSV; omit when order type is a limit variant, or show only the filled price |
| Entered quantity / Filled quantity | `quantity` | CSV has one quantity value; safe to treat entered = filled since Wealthsimple retail orders don't partial-fill in a way this export would show separately |
| Exchange rate | parsed from `description` | not a structured column — FX rate is embedded as free text (`"...FX Rate: 1.4510"`) inside `description`, needs regex extraction during import. Rows for CAD-hedged instruments (e.g. AVGO CDR) have no FX rate in the description since no conversion happens |
| Total cost | `net_cash_amount` | none |

Deliberately **not shown**: "Explore options trading" promo card (Wealthsimple upsell, not applicable), "Download trade confirmation" button (no backend document generation, not applicable) — same treatment as margin requirement, dropped rather than half-built.

## Shared / cross-page

| Component | Used by | Notes |
|---|---|---|
| `StatusBadge` (target-status) | `/wishlist`, `/stocks` | 3-state: above / at / below target |
| Analysis status badge | `/stocks/{id}/analysis` | 4-state: pending / running / done / failed — **kept as a distinct component**, not forced into `StatusBadge`'s 3-state shape |
| `Card` (shadcn) | `/` bentobox tiles, general panel chrome | wrapper only, not a layout mechanism |
| `lib/api.ts` | every page | typed API client wrappers matching `api.md` routes |
| `app/api/proxy/[...path]/route.ts` | every page | Next.js route handler, injects `X-API-Key` server-side — API key never reaches the browser |
| SWR polling | `/wishlist`, `/stocks` (30s); `/stocks/{id}/analysis` (10s, only while any result is pending/running) | refresh intervals differ per page — not uniform |
| `SearchBar` | `/watchlist` (filters the already-loaded wishlist table in place); ticker search (below) is meant to be this in `navigate` mode eventually | Shared shape (text input + live results dropdown), different `mode` prop (`filter` \| `navigate`) — same visual language, but the dropdown must still make clear what selecting a result *does* (narrow the list vs. leave the page), since that behavior genuinely differs between the two modes |
| `Nav` (`components/nav.tsx`) | every page | Top nav bar. Ticker search lives here (top-right, next to the Home/Portfolio/Watchlist links), not scoped to `/portfolio` — applies app-wide since any page can want to jump to a ticker. **Built ahead of #31/backend as a plain `Input` + submit-on-Enter, `router.push('/market/{TICKER}')`** — no live results dropdown, no `validate_ticker` call yet (`/market/[ticker]` doesn't exist yet either, so it currently 404s). Gap to close when #31 is actually built: retrofit onto the shared `SearchBar` component in `navigate` mode, add validation before navigating |

## Design decisions

- **Component library: shadcn/ui** (over Chakra/MUI) — Tailwind-native, no separate theming system to reconcile; you own the component code directly rather than depending on a black-box package. Locked this session; nothing was decided prior.
- **Bentobox layout** — plain CSS Grid + Tailwind, shadcn `Card` for tile styling. Orthogonal concerns; no conflict, nothing to "enable."
- **No drag/resize for tiles** — considered and rejected for MVP. Single-user dashboard (you're both the developer and the only viewer); rearranging tiles by editing `col-span`/`row-span` in JSX is cheaper than building a drag-and-drop layout-persistence system for an audience of one. Revisit only if this becomes multi-user.
- **Chart controls: fixed presets, not free interval+range dropdowns** — `1M`/`1Y`/`3Y`/`ALL` each imply a matching interval, so an invalid combination (e.g. hourly bars over 3 years, which Yahoo's data window can't serve anyway) is structurally impossible rather than something the UI has to validate against.

## Open / pending items

- **Storage tile's backend** — layout/data/component design finalized (see `/` table above), but no backend issue number assigned yet. Needs its own issue covering the Synology DSM API integration, the new NAS monitoring-account credential, its APScheduler polling job, and the TLS decision for DSM's self-signed cert.
