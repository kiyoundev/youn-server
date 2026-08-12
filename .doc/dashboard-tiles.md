# Dashboard Tiles — Data & UX Spec

Working spec for what each dashboard tile shows and why. Frontend is greenfield (no tile components built yet), so this reflects decisions made before implementation, not existing code.

## Key structural decisions

- **Portfolio** = actual stock holdings the user owns.
- **Watchlist** = consumer products only (wishlist-style "notify me when it goes on sale"), *not* stocks. Stocks belong in Portfolio.
- **Schedules** tile is dropped — merged into **Services**. None of the three services has a plain "next scheduled run": the watchlist notifier polls on an interval, the stock price alert is a live connection with a fallback mode, and TradingAgents is trigger-based (manual or conditional), not time-based.
- **Docker** tile stays separate from **Services**. Docker = container-level health (is the Frontend/Backend process up), Services = application-level health (are the individual jobs inside the Backend container actually working). A healthy container can still contain a stuck service.
- Known bug (not a design item): the mockup shows a "TradingAgents · Update" row leaking into the Watchlist tile. Needs to be fixed in data wiring, not designed around.

## Services tile

One row per service. Rows are heterogeneous (different rows need different fields), so render as simple list rows — same convention as the existing Updates/Docker tiles — not a table.

### Row: Watchlist Notifier (polling-based)
- Status dot (healthy / degraded / down)
- Mode label: "Polling"
- Last checked timestamp
- Next check countdown (poll interval)
- Error detail (shown only when unhealthy)

### Row: Stock Price Alert (websocket, tied to Portfolio holdings)
- Status dot
- Mode label: "Live (WS)" or "Fallback (Polling)"
- Last message received timestamp (detects a stale-but-connected socket)
- Fallback poll interval (only relevant while in fallback mode)
- Error/disconnect reason (shown only when unhealthy)

### Row: TradingAgents (trigger-based subprocess)
- Status: Idle / Armed / Running / Error
- Trigger type: Manual launch, or Conditional (show the configured threshold, e.g. "AAPL < $150")
- Last run timestamp + duration
- Last run result summary (success/fail)

## Watchlist tile (consumer products)

Items can be tracked across multiple retailers (e.g. AirPods Max 2 watched on Amazon, Best Buy, and Costco simultaneously), so each item has one summary row with a nested retailer breakdown. Use an accordion: collapsed = glanceable summary, expanded = per-retailer detail.

### Collapsed row (item level)
- Thumbnail
- Product name
- Best current price (lowest across tracked retailers)
- Target price (the "alert me" threshold)
- Alert state: armed / triggered / dismissed

### Expanded content (one row per retailer)
- Retailer name
- Current price (best-price retailer visually highlighted)
- In stock / out of stock
- Last checked timestamp
- Link to product page

### Open question
Alert logic not yet decided: notify when the *lowest* price across all tracked retailers hits target, or let the user pin a specific retailer to watch. Needs an answer before building the notifier's matching logic.

### Layout notes
- Tile has a fixed panel height with internal scroll (matches Storage/Docker tiles) — an expanded accordion row must not grow the outer dashboard grid.
- Consider allowing only one item expanded at a time to avoid long in-tile scrolling.

## Component approach

No shadcn/ui installed yet (greenfield choice, not a constraint from existing code).

- **Services / Updates / Docker**: simple flex/div list rows. Each row's content differs enough (mode, trigger state, etc.) that a table doesn't add value.
- **Watchlist**: leans tabular within each expanded item (retailer, price, stock, last checked are the same columns every time), but doesn't require installing shadcn's `Table` — a plain semantic table/grid styled to match the dark theme is enough unless shadcn gets adopted more broadly for other UI (forms, dialogs, etc.).
