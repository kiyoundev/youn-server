# API

## Authentication

All routes require a shared API key header:

```
X-API-Key: <value of API_KEY env var>
```

Implemented as a FastAPI dependency applied at router-mount time — no per-route decoration needed:

```python
# app/core/auth.py
async def verify_api_key(x_api_key: str | None = Header(None)):
    if x_api_key is None or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

```python
# app/main.py
app.include_router(items_router, dependencies=[Depends(verify_api_key)])
```

`GET /api/health` is exempt from auth — used for uptime checks and Pi boot verification.

**Frontend**: API key stored as server-side env var; all requests proxied through Next.js route handlers — never exposed to the browser.

---

## Routes

### Wishlist Items

One `Product` (shared name + target price) can have many `Listing` rows (one per retailer). `GET /api/items` returns products with their listings nested; product-scoped routes edit the shared name/target price, listing-scoped routes edit one retailer at a time.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/items` | List all products, each with nested `listings[]` |
| `GET` | `/api/items/{product_id}` | Get a single product — 404 if not found |
| `POST` | `/api/items` | Create a new product and, in the same request, as many of `urls` as succeed — body: `{ name, target_price, urls: string[] }` — response: `{ product, failed: [{ url, detail }] }` |
| `POST` | `/api/items/{product_id}/listings` | Add a retailer listing to an existing product — body: `{ url, retailer?, scraper_type? }` — 404 if product not found |
| `PATCH` | `/api/items/{product_id}` | Update shared name/target price — body: `{ name?, target_price? }` — 404 if not found |
| `DELETE` | `/api/items/{product_id}` | Remove product + cascade-delete all listings and price history — 204 on success, 404 if not found |
| `PATCH` | `/api/items/{product_id}/listings/{listing_id}` | Pause/unpause and/or change a listing's URL — body: `{ active?, url?, retailer? }` — preserves the listing's `id` and price history (unlike delete+recreate) — 404 if not found, 409 if `url` collides with another listing |
| `DELETE` | `/api/items/{product_id}/listings/{listing_id}` | Remove one listing. If it was the product's last remaining listing, the now-empty product is deleted too — 204 on success, 404 if not found |
| `GET` | `/api/items/{product_id}/listings/{listing_id}/history` | Price history for one listing — query: `?days=30` — 404 if not found |

**Both POST endpoints** auto-detect `retailer` from URL domain unless explicitly given. If the domain is unknown, they probe the URL via the scraper extraction hierarchy (`HTTPScraper` → `PatchrightScraper`) to determine `scraper_type`, storing `null` if `HTTPScraper` succeeds or `"patchright"` if it needs the headless browser — probing can take several seconds for Patchright-only sites.

- **`POST /api/items/{product_id}/listings`** (single URL) probes synchronously and blocks the request until it finishes. Returns 400 if the URL can't be scraped by either method, 422 if malformed, 409 if `url` already exists anywhere (active or paused, across all products). `scraper_type` in the body overrides auto-detection and skips the probe — only `null`/`"patchright"` are valid, anything else returns 422.
- **`POST /api/items`** (bulk `urls[]`) probes every URL **concurrently**, bounded by an internal semaphore (currently 3 at a time) — total wait is roughly the slowest single probe, not the sum. A duplicate (against an existing listing, or against another URL in the same request) or an unscrapable URL does **not** fail the request — it's reported in the response's `failed: [{ url, detail }]` instead, and the product plus every other successful URL are still created. The whole request only fails outright (409) on the rare commit-time race where a URL was claimed by another request between this one's existing-URL check and its commit. No per-URL `scraper_type`/`retailer` override in this endpoint — those live on the single-listing endpoint above, where they're unambiguous.

`scraper_type` is stored on `Listing` and used internally at poll time (lets the poller skip straight to Patchright for sites that need it, instead of re-trying `HTTPScraper` every cycle) — it is write-only via the API and is not included in `ListingResponse`.

**Computed response fields** — `status` (`watching`/`triggered`/`paused`/`failed`) and `last_checked` are not stored columns; both are computed server-side on every `GET`. `status` priority: all listings inactive → `paused`; else any active listing's last scrape errored → `failed`; else the product has an active alert → `triggered`; else `watching`. Stock availability (`ok`/`oos`/`error`) is tracked per listing via `last_scrape_status` and surfaced independently — it does not affect product-level `status`.

### Stock Alerts

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/stockalerts` | List all stock alerts |
| `GET` | `/api/stockalerts/{id}` | Get a single stock alert — 404 if not found |
| `POST` | `/api/stockalerts` | Add alert — body: `{ ticker, target_price, direction, alert_type?, run_analysis?, deep_think_llm?, quick_think_llm?, anthropic_effort?, max_debate_rounds?, max_risk_discuss_rounds?, analysts? }` |
| `PATCH` | `/api/stockalerts/{id}` | Update — body: same optional fields as `POST` — 404 if not found |
| `DELETE` | `/api/stockalerts/{id}` | Remove alert — 204 on success, 404 if not found |
| `POST` | `/api/stockalerts/{id}/analyze` | Manually trigger TradingAgents for this ticker — 404 if alert not found |
| `GET` | `/api/stockalerts/{id}/analysis` | List analysis results — query: `?limit=10` — 404 if alert not found |

**Current consumer:** `/portfolio`'s Watchlist tile reads `GET /api/stockalerts` — but the endpoint itself is generic (all alerts, no section/tile scoping), it's just the only thing calling it today. Config data only (target price, direction, `run_analysis`, etc.) — a separate, richer, ticker-scoped (not alert-scoped) market-data endpoint is planned for the detail page and Popular Assets, not yet built: see `.doc/issues.md` `#19` (`Position`/Holdings), `#30` (`/api/market/trending`, Popular Assets), `#31` (`/api/market/{ticker}/details`, works for any ticker regardless of whether it has an alert).

`direction`: `"above"` or `"below"`. **POST** validates ticker via Finnhub REST on creation — returns 400 if invalid, 409 if an alert for this `(ticker, direction, alert_type)` triple already exists (active or paused). (yfinance is used only for `/history`-style chart data, not validation.)

`alert_type`: `"buy_signal"` (default), `"stop_loss"`, or `"take_profit"`. Because uniqueness is `(ticker, direction, alert_type)` rather than just `(ticker, direction)`, the same ticker can carry multiple alert types in the same direction at different prices — e.g. `AAPL below $90` (buy the dip, `buy_signal`) and `AAPL below $70` (hard stop, `stop_loss`), or `AAPL above $150` (lock in gains, `take_profit`). A `stop_loss` crossing sends a distinctly-worded push at Pushover **High** priority (bypasses quiet hours/DND); `take_profit` also gets distinct wording but stays at Normal priority — see `.doc/notifications.md`.

**TradingAgents per-alert config:** `llm_provider` and `output_language` are global (`TRADINGAGENTS_LLM_PROVIDER` / `TRADINGAGENTS_OUTPUT_LANGUAGE` env vars, same for every alert). `deep_think_llm`, `quick_think_llm`, `anthropic_effort` (`"high" | "medium" | "low"`), `max_debate_rounds`, `max_risk_discuss_rounds`, and `analysts` (subset of `"market" | "social" | "news" | "fundamentals"`) are per-alert — settable via `POST`/`PATCH`. Each is independently nullable; `null` means "inherit the global env default." On `PATCH`, a field must be explicitly included (even as `null`) to change it — an omitted field is left untouched.

**POST /api/stockalerts/{id}/analyze** is a debug/manual-trigger tool — the real usage path is automatic (threshold crossing + `run_analysis=true`). It runs regardless of threshold or `run_analysis` flag, using `alert.last_price` as `triggered_price` (no live price fetch — `last_price` may be `null` if this alert has never fired, in which case `triggered_price` is stored as `null`). Creates an `AnalysisResult` row with `status: "pending"` and returns it immediately, spawning the TradingAgents run in the background. Returns 409 if an analysis is already running for this ticker.

**Live progress while `status: "running"`:** `GET /api/stockalerts/{id}/analysis` reflects `llm_calls`, `tokens_in`, `tokens_out`, `tool_calls`, and `last_heartbeat_at`, updated as the subprocess emits heartbeat lines — an idle timer (`tradingagents_idle_timeout_seconds`, default 10min) resets on each heartbeat rather than killing the run on a flat total-elapsed timeout. A hard cap (`tradingagents_hard_cap_seconds`, default 2h) applies regardless of heartbeats. On `status: "failed"`, `error_reason` distinguishes `"idle_timeout"` / `"subprocess_error"` / `"invalid_output"` / `"max_runtime_exceeded"`.

### Activities (Wealthsimple Import)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/activities/import` | Import a Wealthsimple "activities export" CSV — `multipart/form-data`, one `file` field — response: `{ accounts: AccountImportResult[] }` — 422 with a structured `detail` on any rejection |
| `DELETE` | `/api/activities` | Reset one account's ledger — query: `?account_id=` (required) — response: `{ account_id, deleted }` |

**POST /api/activities/import** turns an export into a durable ledger of `Activity` rows (issue #33). The ledger is the source of truth — there is no `Position` table; holdings, average cost and cash are derived on read (`services/positions.py`). Wealthsimple exports carry no row id and cap at 12 months, so uploads overlap and rows can't be matched. Merging rests on date ranges instead, per `account_id`:

- **Frozen past** — stored rows older than (newest stored date − 7 days) are never touched; the file's copies of them are skipped. That's what makes re-uploading the same file safe.
- **Tail refresh** — only when the file reaches the newest stored row: from the boundary onward, stored rows are deleted and replaced wholesale by the file's rows (covers late-settling trades and half-day exports). A row dated exactly on the boundary counts as tail. A file that ends *before* the newest stored row (say, re-uploading an older export) never deletes anything — whatever it has in the tail window is skipped and the tail stays exactly as stored.
- **Prepend** — rows older than the earliest stored date are added, so older history can be imported later. This is **not** checked for contiguity: a file containing only older rows is accepted even if it leaves a gap before the earliest stored row (a deliberate deviation from the original spec's "contiguous on the older side" — an account's history starts at its first deposit, so there's normally nothing older to import; enforce it if that ever changes).
- **Reach-back** — a file that reaches the newest stored row must also reach back to the boundary, or it's rejected with `coverage_gap` and the date to re-export from. A file that ends earlier isn't replacing the tail, so it can't leave a hole in it and isn't checked.

Writes to one account are serialized with a transaction-scoped Postgres advisory lock (also taken by the reset route), so two overlapping imports can't both plan against the same stored range and double-insert — there's no unique key to catch that. Everything is parsed and validated first, then `compute_positions` runs on the merged ledger as an integrity check (cash or shares going negative, or one symbol mixing FX-present and FX-absent trades, rejects the file) — all before anything is written. The write is **one transaction across every account in the file**: either all of it lands or none of it does. The calendar dates written into `message` and the `coverage_gap` text are `America/Toronto` dates (the ledger's own timezone), not UTC — a 23:41 local deposit is still that day. Timestamps in `coverage` and in error extras are ISO instants with an offset.

Response, per account — `{ account_id, added, replaced, skipped, coverage: { earliest, newest }, message, warnings }`. `added` = rows new to the ledger outside the refreshed tail (every row on a first import, otherwise only rows older than the previous earliest date); `replaced` = rows written into the refreshed tail; `skipped` = frozen rows ignored. `message` is `"Ledger runs A → B; next time export from B − 7 days or earlier."` and `warnings` currently carries at most "ledger doesn't start with a funding deposit" (non-fatal).

**Rejections** are all `422`, with `detail: { code, message, ...extras }` (datetimes in extras are ISO strings) and nothing written:

| `code` | When | Extras |
|--------|------|--------|
| `invalid_file` | upload isn't valid UTF-8, or the `csv` module can't read it (e.g. a large non-CSV text file) | — |
| `missing_columns` | required header columns absent | `missing: string[]` |
| `empty_file` | header but no data rows | — |
| `malformed_row` | unparseable number or date on a row | `line`, `field?` |
| `missing_effective_date` | a row has a blank `effective_date`/`effective_time` (not backfilled from `settlement_date`) | `line` |
| `unsupported_currency` | a row's `currency` isn't `CAD` (every row is stamped CAD, even USD stock trades — a USD holding is detected from `FX Rate:` text in the description instead) | `line`, `currency` |
| `unknown_activity_type` | an `(activity_type, activity_sub_type)` pair isn't in the confirmed allowlist | `types: [{ activity_type, activity_sub_type, direction, count, example }]` |
| `coverage_gap` | file reaches the tail but not back to the boundary | `re_export_from` |
| `negative_cash` | running cash balance goes below 0 — earlier history is likely missing | `date` |
| `negative_holdings` | a sell exceeds the shares held | `account_id`, `symbol`, `date` |
| `mixed_native_currency` | one symbol has trades both with and without an FX rate | `account_id`, `symbol` |

An upload over 5 MB is refused with **`413`** and `{ code: "file_too_large", message }` before anything is parsed (a real export is tens of KB). FastAPI's own validation failure (no `file` field) is also `422` but with `detail` as an array of `{ type, loc, msg, input }`; a proxy with no `API_KEY` is a `500` with a string `detail`.

Only `Trade`/`BUY`, `MoneyMovement`/`EFT`, `MoneyMovement`/`E_TRFIN`, `Interest`, `Dividend` and `Tax`/`NRT` rows are recognized. **A sell is rejected as `unknown_activity_type` on purpose** — its real `activity_sub_type`/`direction` strings haven't been seen yet; the rejection's `types` entry carries the exact strings to map once one appears (and `negative_holdings` can't fire until then). Rejecting the whole file rather than skipping the row keeps a later re-upload working — a skipped row would be stranded by the frozen-past rule.

**DELETE /api/activities** deletes every `Activity` row for one `account_id` — the recovery path for the frozen-past limitation (a correction to an already-frozen row is never picked up by a normal import, so it needs a reset and a full re-import). Backend-only: no frontend caller, deliberately — it's rare and destructive enough that a `curl` with the API key is the right amount of friction. Deleting an account with no rows returns `deleted: 0`.

There is no read endpoint for holdings here — `GET /api/positions` and the rest belong to `.doc/issues.md` `#19`, which calls `compute_positions` against the committed rows.

**Frontend**: the Upload button in the nav POSTs the file to `/api/proxy/activities/import` — a dedicated route handler, not the JSON catch-all `[...path]`, which forces `Content-Type: application/json` and would corrupt the multipart boundary. It forwards the raw body and `Content-Type` verbatim (buffered, not streamed) with the `X-API-Key` added server-side. It refuses an oversized upload up front (`413`, from `Content-Length`, before buffering it) and gives the backend 30 seconds — a timeout answers `504` and an unreachable backend `502`, each with a plain string `detail`. Success shows an "Import complete" toast; a rejection shows the `message` in a persistent error toast, with the full `detail` logged to the browser console.

### TradingAgents Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/analysis/tradingagents/version` | Compare the local `/opt/tradingagents` clone against `origin/main` |
| `POST` | `/api/analysis/tradingagents/update` | `git pull` + reinstall deps in the TradingAgents venv |

**GET /api/analysis/tradingagents/version** runs `git fetch origin` then compares commits. Returns `{ available: false }` if `/opt/tradingagents` isn't cloned yet, or `{ available: false, error }` if `git fetch` fails (e.g. no network) — otherwise `{ current_commit, current_date, latest_commit, latest_date, behind_count, update_available }`.

**POST /api/analysis/tradingagents/update** runs `git pull` in `/opt/tradingagents`, then `pip install -r requirements.txt` in its venv so dependencies never drift from the cloned code. Returns `{ success, new_commit, output }` — `output` is the combined stdout/stderr of both steps. Trusts upstream `TauricResearch/tradingagents`; only call when an update is actually expected.


### Manual Poll Triggers

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/poll/prices` | Trigger price scraping job immediately |
| `POST` | `/api/poll/stocks` | Force a REST re-check of all actively-watched tickers |

`/api/poll/prices` runs `poll_prices()` — same job as the scheduled 6h cycle. `/api/poll/stocks` is a manual fallback alongside the always-on Finnhub WebSocket stream: it re-checks current prices via Finnhub REST and runs the same threshold logic the WS path uses, in case a price movement was missed during a brief WS disconnect.

Both endpoints fire a background task and return immediately — results are not included in the response (check `GET /api/items`, `/api/items/{id}/history`, or `GET /api/stockalerts` afterward). Both are guarded by an in-memory "already running" lock (prevents overlapping cycles with each other or the scheduled job) and rate-limited to 1 call per 5 minutes (in-memory timestamp).

- Success: `200` — `{ "status": "queued" }`
- Rate-limited: `429` — `{ "detail": "Rate limited, try again in Ns" }`

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/system/storage` | Synology NAS bay + volume storage status |

**GET /api/system/storage** reads live from the Synology NAS over DSM's webapi (`SYNO.API.Auth` login → `SYNO.Storage.CGI.Storage` query → logout) — no caching, one DSM session per call. Returns per-bay status (`"empty" | "healthy" | "warning" | "error"`) plus `available`/`used`/`reserved` capacity in TB. Returns 503 if `synology_host`/`synology_user`/`synology_password` are unset or the NAS is unreachable.

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Returns `{ status: "ok" }` — no auth required |

---

## TypeScript Interfaces

```typescript
export interface WatchItem {
  id: number;
  name: string;
  url: string;
  retailer: string;
  target_price: number;
  last_price: number | null;
  alerted_at: string | null;
  active: boolean;
  created_at: string;
}

export interface PriceHistory {
  id: number;
  watch_item_id: number;
  price: number;
  checked_at: string;
}

export interface StockAlert {
  id: number;
  ticker: string;
  target_price: number;
  direction: "above" | "below";
  alert_type: "buy_signal" | "stop_loss" | "take_profit";
  last_price: number | null;
  alerted_at: string | null;
  active: boolean;
  run_analysis: boolean;
  deep_think_llm: string | null;
  quick_think_llm: string | null;
  anthropic_effort: "high" | "medium" | "low" | null;
  max_debate_rounds: number | null;
  max_risk_discuss_rounds: number | null;
  analysts: ("market" | "social" | "news" | "fundamentals")[] | null;
  created_at: string;
}

export interface AnalysisResult {
  id: number;
  stock_alert_id: number;
  event_id: number | null;
  ticker: string;
  triggered_price: number | null;
  result: Record<string, unknown> | null;
  status: "pending" | "running" | "done" | "failed";
  action: string | null;
  price_target: number | null;
  report_path: string | null;
  llm_calls: number;
  tokens_in: number;
  tokens_out: number;
  tool_calls: number;
  last_heartbeat_at: string | null;
  error_reason: "idle_timeout" | "subprocess_error" | "invalid_output" | "max_runtime_exceeded" | null;
  created_at: string;
  completed_at: string | null;
}

export interface TradingAgentsVersion {
  available?: false;
  error?: string;
  current_commit?: string;
  current_date?: string;
  latest_commit?: string;
  latest_date?: string;
  behind_count?: number;
  update_available?: boolean;
}

export interface Event {
  id: number;
  type: "PRICE_DROP" | "STOCK_THRESHOLD";
  payload: Record<string, unknown>;
  status: "pending" | "processed" | "failed";
  created_at: string;
  processed_at: string | null;
}

export interface BayStatus {
  label: string;
  status: "empty" | "healthy" | "warning" | "error";
}

export interface StorageResponse {
  bays: BayStatus[];
  available: number; // TB
  used: number; // TB
  reserved: number; // TB
}

// POST /api/activities/import — mirrors frontend/src/lib/api/activities.ts
export interface AccountImportResult {
  account_id: string;
  added: number;
  replaced: number;
  skipped: number;
  coverage: { earliest: string; newest: string };
  message: string;
  warnings: string[];
}

export interface ImportResult {
  accounts: AccountImportResult[];
}
```
