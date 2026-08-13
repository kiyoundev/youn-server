# youn-server — Issue Backlog

Generated from: `.doc/PRD.md`, `.doc/architecture.md`, `.doc/database.md`, `.doc/api.md`, `.doc/scraping.md`, `.doc/notifications.md`, `.doc/security.md`

All issues are AFK unless marked HITL (requires manual action or external decision outside the codebase).

---

## System Flow

```
APScheduler (price poll every 6h)
    └── scrape WatchItem URLs → write PriceHistory → detect price drop
            └── INSERT events { type: "PRICE_DROP", status: "pending" }

FinnhubClient WebSocket (persistent connection, started on lifespan)
    └── price tick received → check active StockAlert thresholds
            └── threshold crossed → INSERT events { type: "STOCK_THRESHOLD", status: "pending" }

Single dispatcher (asyncio.Queue listener, started in lifespan)
    ├── PRICE_DROP → send_alert() → mark processed
    └── STOCK_THRESHOLD → send_alert() → if run_analysis=true
                            → create AnalysisResult { status: "pending" }
                            → (Issue #9) spawn TradingAgents subprocess
                                       → store result → follow-up push
```

---

## Progress Tracker

| Status | ID | Description | Type | Est. | Blocked by |
|---|---:|---|---|---|---|
| ✅ Done | #1 | Project Scaffolding + Docker Compose | feat / AFK | ~3h | None |
| ✅ Done | #1.5 | Synology NAS — PostgreSQL Setup (native DSM package) | ops / HITL | ~1h | None |
| ✅ Done | #2 | Database Models + Alembic Migrations | feat / AFK | ~2h | #1, #1.5 |
| ✅ Done | #3 | Scraping Layer | feat / AFK | ~6h | #1, #2 |
| ✅ Done | #4 | Stock Price Service (Finnhub WebSocket + REST) | feat / AFK | ~3h | #1, #2 |
| ✅ Done | #5 | Notification Service (Pushover + Email) | feat / AFK | ~2h | #1, #2 |
| ✅ Done | #6 | APScheduler Jobs + Event Queue Writes | feat / AFK | ~3h | #2, #3, #4 |
| ✅ Done | #7 | Event Consumers (Notify + Analysis stub) | feat / AFK | ~3h | #5, #6 |
| ✅ Done | #8 | FastAPI Routes + Auth | feat / AFK | ~4h | #2, #3, #4, #5, #7 |
| ✅ Done | #9 | TradingAgents Integration | feat / AFK | ~5h | #7, #8 |
| ✅ Done | #24 | Wishlist Product/Listing Model (Multi-Retailer Grouping) | feat / AFK | ~6h | #8 |
| ✅ Done | #10.1 | ~~Wishlist Page (Read-Only)~~ | feat / AFK | ~2h | #8, #24 |
| ✅ Partially Done (Testing Skipped) | #10.2 | Wishlist Mutations (Add/Edit/Pause/Delete) | feat / AFK | ~2h | #36 |
| ✅ Done | #10.3 | ~~Price History Chart~~ | feat / AFK | ~1.5h | #10.1 |
| ✅ Done | #10.4 | Stock Alert Alarm (Market Detail Sheet) | feat / AFK | ~2h | #36 |
| ✅ Done | #10.5 | Navigation | feat / AFK | ~0.5h | #10.1, #10.4 |
| ⬜ Open | #10.6 | Ticker Watchlist (Star, Persisted) | feat / AFK | ~2h | #10.4 |
| ⬜ Open | #11 | Analysis Results UI | feat / AFK | ~3h | #9, #10.1–#10.5 |
| ~~❌ Removed~~ | ~~#12~~ | ~~iOS SwiftUI Token Registration App~~ | ~~feat / HITL~~ | ~~#8~~ | ~~Replaced by Pushover~~ |
| ⬜ Open | #13 | Pi Deployment + Tailscale | ops / HITL | ~3h | #8, #10.1–#10.5 |
| ⬜ Open | #13.1 | Tailscale Subnet Routing (NAS Postgres Reachability) | ops / HITL | ~0.75h | None |
| ⬜ Open | #14 | Integration Tests | test / AFK | ~4h | #3, #4, #5, #7, #8 |
| ⬜ Open | #15 | Headless Chromium Bot Detection on Pi | ops / AFK | ~2h | #3, #13 |
| ⬜ Open | #16 | Tailscale MagicDNS (Human-Readable Hostnames) | ops / HITL | ~0.5h | #13 |
| ✅ Done | #17 | TradingAgents Progress Heartbeat + Idle Timeout | feat / AFK | ~2h | #9 |
| ⬜ Open | #18 | DB Connection Resilience (pool_pre_ping + Pending-Event Rescan) | feat / AFK | ~1.5h | #6, #7 |
| ⬜ Open | #19 | Manual Portfolio Position Tracking | feat / AFK | ~4h | #8, #10.1–#10.5 |
| ⬜ Open | #20 | youn-server Self-Update (Version Check + Auto-Apply) | feat / AFK | ~3h | #8, #13 |
| ⬜ Open | #21 | System/Infra Status API (Docker, Pi Resources, Services, Schedules) | feat / AFK | ~3h | #8, #20 |
| ✅ Done | #21.5 | Synology Storage Status API | feat / AFK | ~1h | #1.5 |
| ⬜ Open | #22 | Overview Dashboard (`/`, Bentobox Summary) | feat / AFK | ~4h | #10.1–#10.5, #11, #19, #20, #21 |
| ⬜ Open | #23 | Stock Price History Chart (Portfolio) | feat / AFK | ~3h | #19 |
| ⬜ Open | #25 | Claude OAuth Auth Working in Docker | feat / AFK | ~1h | None |
| ⬜ Open | #26 | Per-Report Chat Backend (Non-Streaming) | feat / AFK | ~4h | #8, #25 |
| ⬜ Open | #27 | Streaming Chat Responses | feat / AFK | ~1.5h | #26 |
| ⬜ Open | #28 | Chat UI | feat / AFK | ~3h | #27, #11 |
| ⬜ Open | #29 | Frontend Test Suite (Vitest Setup + Watchlist Components + Proxy Route) | test / AFK | ~3h | None |
| ⬜ Open | #30 | Trending/Popular Assets (Portfolio) | feat / AFK | ~4h | #19 |
| ✅ Done | #31 | Ticker Detail Page (Market Details Navigation) | feat / AFK | ~5h | #19, #23, #30 |
| ✅ Done | #34 | DNS-Based Ad Blocking (Pi-hole) | ops / HITL | ~1h | None |
| ✅ Done | #36 | Wishlist Page (Real Data + Live Price History via SSE) | feat / AFK | ~6h | #8, #24 |
| ⬜ Open | #37 | Stocks/Portfolio Page — Live Updates via SSE (Finnhub Tick Broadcast) | feat / AFK | ~4h | #36, #10.4 |
| ⬜ Open | #38 | Earnings Calendar (Portfolio Page + Ticker Detail Page) | feat / AFK | ~3h | #19, #31 |

**Total estimated:** ~102.75h *(was ~61h — saved ~12h by switching to Pushover: #5 reduced 8h→2h, #12 removed 6h, #13 no longer needs APNs key setup; +6h for #21/#22 overview dashboard, +3h for #23 stock history chart, +1h for #21's services/schedules tiles, +1h for #21.5 Synology storage status API; +6h for #24 wishlist Product/Listing model split; +9.5h for #25–#28 AI chat feature; +3h for #29 frontend test suite; +1h for #34 DNS ad blocking; #10.1 (~2h) + #10.3 (~1.5h) merged into #36 (~6h) — net +2.5h for SSE backend surface: broadcast hook, streaming route, streaming proxy, frontend EventSource wiring; +4h for #37 extending SSE to stock ticks; +3h for #38 earnings calendar; +2h for #10.6 ticker watchlist, split out of #10.4 mid-implementation once the star icon was found to be the real watchlist-membership mechanism; +0.75h for #13.1 Tailscale subnet routing, split out of #13 once discovered the NAS isn't itself a Tailscale node and needs a subnet route through the Pi)*

---

## Recommended Work Order

| Step | ID | Description | Est. | Blocked by |
|---:|---|---|---|---|
| 1 | **#1** | Project scaffolding + Docker | ~3h | — |
| 2 | **#2** | DB models + migrations | ~2h | #1 |
| 3 | **#3, #4, #5** | Scraping, stocks, notifications (parallel) | ~2–6h | #2 |
| 4 | **#6** | Scheduler jobs + event writes | ~3h | #3, #4 |
| 5 | **#7** | Event consumers | ~3h | #5, #6 |
| 6 | **#8** | FastAPI routes + auth | ~4h | #7 |
| 7 | **#14** | Integration tests | ~4h | #8 |
| 8 | **#24** | Wishlist Product/Listing model (multi-retailer grouping) | ~6h | #8 |
| 9 | **#36** | Wishlist page (real data + live price history via SSE) — merges former #10.1, #10.3 | ~6h | #8, #24 |
| 10 | **#10.2** | Wishlist mutations (add/edit/pause/delete) | ~2h | #36 |
| 12 | **#10.4** | Stock alert alarm (market detail sheet) | ~2h | #36 |
| 12.5 | **#37** | Stocks/portfolio live updates via SSE (Finnhub tick broadcast) | ~4h | #36, #10.4 |
| 14.5 | **#38** | Earnings calendar (portfolio page + ticker detail page) | ~3h | #19, #31 |
| 13 | **#10.5** | Navigation | ~0.5h | #10.1, #10.4 |
| 13.5 | **#10.6** | Ticker watchlist (star, persisted) | ~2h | #10.4 |
| 14 | **#9** | TradingAgents integration | ~5h | #7, #8 |
| 15 | **#11** | Analysis results UI | ~3h | #9, #10.1–#10.5 |
| 16 | **#13** | Pi deployment + Tailscale | ~3h | #10.1–#10.5 |
| 16.5 | **#13.1** | Tailscale subnet routing (NAS Postgres reachability) | ~0.75h | — |
| 17 | **#16** | Tailscale MagicDNS (human-readable hostnames) | ~0.5h | #13 |
| 18 | **#17** | TradingAgents progress heartbeat + idle timeout | ~2h | #9 |
| 19 | **#18** | DB connection resilience | ~1.5h | #6, #7 |
| 20 | **#19** | Manual portfolio position tracking | ~4h | #8, #10.1–#10.5 |
| 21 | **#20** | youn-server self-update (check + auto-apply) | ~3h | #8, #13 |
| 22 | **#21** | System/infra status API (Docker, Pi resources, services, schedules) | ~3h | #8, #20 |
| 23 | **#22** | Overview dashboard (`/`, bentobox summary) | ~4h | #10.1–#10.5, #11, #19, #20, #21 |
| 24 | **#23** | Stock price history chart (portfolio) | ~3h | #19 |
| 25 | **#25** | Claude OAuth auth working in Docker | ~1h | — |
| 26 | **#26** | Per-report chat backend (non-streaming) | ~4h | #8, #25 |
| 27 | **#27** | Streaming chat responses | ~1.5h | #26 |
| 28 | **#28** | Chat UI | ~3h | #27, #11 |
| 29 | **#29** | Frontend test suite (Vitest setup + watchlist components + proxy route) | ~3h | — |

---

## Dependency Graph

**Group 0 — Foundation**

```
#1 — Project Scaffolding + Docker     [no deps — start here]
  └── #2 — Database Models + Migrations
```

**Group 1 — Core Services (parallel after #2)**

```
#2
  ├── #3 — Scraping Layer
  ├── #4 — Stock Price Service
  └── #5 — Notification Service
```

**Group 2 — Scheduling + Event Queue**

```
#2, #3, #4
  └── #6 — APScheduler Jobs + Event Queue Writes
        └── #7 — Event Consumers     [also needs #5]
              └── #18 — DB Connection Resilience     [also needs #6]
```

**Group 3 — API**

```
#2, #3, #4, #5, #7
  └── #8 — FastAPI Routes + Auth
```

**Group 4 — AI Analysis**

```
#7, #8
  └── #9 — TradingAgents Integration
        └── #17 — TradingAgents Progress Heartbeat + Idle Timeout
```

**Group 4.5 — Wishlist Data Model**

```
#8
  └── #24 — Wishlist Product/Listing Model (Multi-Retailer Grouping)
```

**Group 5 — Frontend**

```
#8, #24
  └── #36 — Wishlist Page (Real Data + Live Price History via SSE)   [merges former #10.1, #10.3]
        ├── #10.2 — Wishlist Mutations (Add/Edit/Pause/Delete)
        └── #10.4 — Stock Alert Alarm (Market Detail Sheet)
              ├── #10.5 — Navigation   [also needs #36]
              ├── #10.6 — Ticker Watchlist (Star, Persisted)
              └── #37 — Stocks/Portfolio Live Updates via SSE   [also needs #36]

#10.1–#10.5
  ├── #11 — Analysis Results UI   [also needs #9]
  └── #19 — Manual Portfolio Position Tracking
```

**Group 6 — Deployment**

```
#8, #10.1–#10.5
  └── #13 — Pi Deployment + Tailscale   [HITL: physical Pi + Tailscale account]
        ├── #16 — Tailscale MagicDNS (Human-Readable Hostnames)
        └── #20 — youn-server Self-Update (Version Check + Auto-Apply)
```

**Group 8 — Testing**

```
#3, #4, #5, #7, #8
  └── #14 — Integration Tests

[no deps — start here]
  └── #29 — Frontend Test Suite (Vitest Setup + Watchlist Components + Proxy Route)
```

**Group 9 — AI Chat** (kept separate from Group 4 — different trigger model, different auth model, no shared code path)

```
[no deps — start here]
  └── #25 — Claude OAuth Auth Working in Docker

#8, #25
  └── #26 — Per-Report Chat Backend (Non-Streaming)
        └── #27 — Streaming Chat Responses
              └── #28 — Chat UI   [also needs #11]
```

**Critical path:** `#1 → #2 → #3/#4/#5 → #6 → #7 → #8 → #24 → #36 → #10.4 → #10.5 → #13`

Group 9 doesn't sit on the critical path — it branches off #8 independently of the deployment chain.

**Start immediately (no blockers):** `#1`, `#25`, `#29`, `#34`

---

## Group 0 — Foundation

---

## [x] Issue #1 — Project Scaffolding + Docker Compose

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** None — start here

### What to build

Create the full monorepo directory structure and bootstrap both sub-projects. Wire Docker Compose for ARM64 Pi deployment with correct base images.

- `backend/`: Python 3.12 project (`pyproject.toml`, `.python-version`, `requirements.txt`)
- `frontend/`: Next.js 14 App Router (`npx create-next-app@latest --typescript --tailwind --app`)
- `docker-compose.yml`: backend + frontend services, `platform: linux/arm64`, shared `.env`, `restart: unless-stopped`
- `.env.example`: all required keys — `API_KEY`, `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `FINNHUB_API_KEY`, `CORS_ORIGINS`, `DATABASE_URL`
- `backend/Dockerfile`: `mcr.microsoft.com/playwright/python` base image (ARM64 Chromium), installs dependencies
- `frontend/Dockerfile`: `node:20-alpine` multi-stage build
- Both containers run as non-root (`USER 1000`)
- `.gitignore`: excludes `.env`, `db.sqlite`, `.doc/`

### Acceptance criteria

- [x] `docker compose up` starts both services without error on ARM64
- [x] `backend/` Python project installs cleanly with `pip install -r requirements.txt`
- [x] `frontend/` Next.js app starts at `localhost:3000`
- [x] `.env.example` contains all required keys with placeholder values
- [x] Docker image does not contain `.env` (verified via `docker inspect`)
- [x] Both containers run as UID 1000, not root

---

## [✅] Issue #1.5 — Synology NAS: Full Setup (PostgreSQL + Plex + Network)

**Type:** ops / HITL
**Estimate:** ~2h
**Blocked by:** None — can do any time before #2 migration verification
**HITL reason:** Requires DSM browser access to Synology NAS (DS718+, DSM 7.1.1).

### What to build

Full NAS setup: static IP reservation, admin user, SSH, PostgreSQL for the backend, and Plex Media Server.

---

**Step 1 — Reserve static IP (do this first)**
- Open Eero app → Devices → tap NAS → "Reserve IP"
- This ensures NAS always gets the same IP from DHCP (no more IP changes on reboot)
- Note the reserved IP — this becomes `<nas-ip>` in all config below

**Step 2 — Create a named admin user (so you're not relying on `admin`)**
- DSM → Control Panel → User & Group → Create
- Add to `administrators` group
- Write down username + password somewhere

**Step 3 — Enable SSH**
- DSM → Control Panel → Terminal & SNMP → Enable SSH service → Port 22
- You'll need this to configure PostgreSQL config files

**Step 4 — Install packages via Package Center**
- DSM → Package Center → install:
  - **PostgreSQL 14** (or latest available)
  - **Plex Media Server**

**Step 5 — Create Shared Folders**
- DSM → Control Panel → Shared Folder → Create:
  - `media` — for Plex libraries (movies, TV, music)
- Plex will use this folder as its library root

**Step 6 — Configure PostgreSQL for remote access**

SSH into NAS:
```bash
ssh <your-admin-user>@<nas-ip>
```

Find the PostgreSQL data directory (usually `/volume1/@database/pgsql/`) and edit:

```bash
# Find exact paths
sudo find /volume1 -name "postgresql.conf" 2>/dev/null
sudo find /volume1 -name "pg_hba.conf" 2>/dev/null
```

Edit `postgresql.conf`:
```
listen_addresses = '*'
```

Edit `pg_hba.conf` — add line:
```
host    youn_server    youn    0.0.0.0/0    md5
```
(Restrict to Pi LAN IP once known: `<pi-ip>/32`)

**Step 7 — Create database and user**
```bash
sudo -u postgres psql
CREATE USER youn WITH PASSWORD 'change_me';
CREATE DATABASE youn_server OWNER youn;
\q
```

**Step 8 — Restart PostgreSQL**
- DSM → Package Center → PostgreSQL → Stop → Start

**Step 9 — Add to `backend/.env`:**
```
DATABASE_URL=postgresql+asyncpg://youn:change_me@<nas-ip>/youn_server
```

**Step 10 — Test connection:**
```bash
psql postgresql://youn:change_me@<nas-ip>/youn_server -c "SELECT 1"
```

### Acceptance criteria

- [x] NAS has reserved IP in Eero — never changes on reboot
- [x] Named admin user created (not relying on `admin` account)
- [x] SSH enabled on port 22
- [x] PostgreSQL package installed and running
- [x] `media` shared folder created for Plex
- [x] Plex Media Server installed and accessible at `http://<nas-ip>:32400/web`
- [x] `youn_server` database exists, owned by `youn` user
- [x] `psql` connection from dev machine / Pi succeeds on NAS LAN IP
- [x] `backend/.env` has `DATABASE_URL` pointing to reserved NAS IP

---

## [✅] Issue #2 — Database Models + Alembic Migrations

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #1

### What to build

Define all SQLAlchemy ORM models and generate the initial Alembic migration. Wire the DB session into FastAPI.

**Models:** `WatchItem`, `PriceHistory` (CASCADE DELETE from WatchItem), `StockAlert` (with `run_analysis: bool = False`), `Event`, `AnalysisResult`

- `core/db.py`: async SQLAlchemy engine from `DATABASE_URL` env var (Postgres via asyncpg)
- `core/config.py`: `pydantic-settings` `Settings` class loading all env vars
- Alembic init + `env.py` wired to SQLAlchemy models
- Initial migration auto-generated and verified against all five models
- Pydantic response schemas (separate from ORM models) for each model

### Acceptance criteria

- [x] `alembic upgrade head` creates all five tables without error
- [x] `WatchItem` delete cascades to `PriceHistory` rows
- [x] `StockAlert.run_analysis` defaults to `False`
- [x] `Event.status` defaults to `"pending"`
- [x] Pydantic schemas exist for all five models and match ORM field names

---

## Group 1 — Core Services

---

## [✅] Issue #3 — Scraping Layer

**Type:** feat / AFK
**Estimate:** ~6h
**Blocked by:** #1, #2

### What to build

Build the complete scraping layer: abstract base class, two concrete scraper implementations, shared universal extraction methods, a typed result, and a domain router. Any product URL is supported without site-specific config — extraction hierarchy tries standardized methods in order.

**`ScraperResult` dataclass:**
- `price: float | None` — `None` if price not found or item OOS
- `status: Literal["ok", "oos", "error"]` — distinguishes out-of-stock from scraper failure

**Classes:**
- `BaseScraper` ABC: `async def get_price(url: str) -> ScraperResult`; shared extraction methods and price utilities
- `HTTPScraper(BaseScraper)`: httpx GET with rotating User-Agent pool + realistic headers; runs extraction hierarchy on response HTML
- `PatchrightScraper(BaseScraper)`: headless Chromium via `patchright`; patches CDP-level automation signals; runs same extraction hierarchy on rendered DOM; shared browser instance per job run; closed after job completes
- `AmazonCAScraper(PatchrightScraper)`: explicit CSS selector for price (whole + fraction concatenated); 2 retries before returning `ScraperResult(price=None, status="error")`

**Extraction hierarchy (tried in order, shared `BaseScraper` methods):**
1. `_extract_shopify()` — `GET /products/{handle}.json`; extracts price from variant matching `?variant=` URL param, or `variants[0].price`; checks `available` field → `status="oos"`
2. `_extract_jsonld()` — `<script type="application/ld+json">` → `offers.price`; checks `offers.availability` for `schema.org/OutOfStock` → `status="oos"`
3. `_extract_og_price()` — `<meta property="og:price:amount">`
4. `_extract_nextdata()` — recursive heuristic search through `__NEXT_DATA__` JSON for numeric "price" key; `NEXTDATA_PATHS` override dict for stores where heuristic picks wrong value

**Routing:**
- `RetailerRouter`: `amazon.ca` → `AmazonCAScraper`; all other domains → `HTTPScraper`; if `HTTPScraper` returns `status="error"` → retry with `PatchrightScraper` (handles JS-rendered + bot-blocked sites)
- `RETAILER_MAP`: only `amazon.ca` explicitly wired

**Config dicts:**
- `SELECTORS`: `{"amazon_ca": "..."}` — whole + fraction selector concatenated; no other entries needed
- `NEXTDATA_PATHS`: empty by default; add entries only when `_extract_nextdata()` heuristic picks wrong value for a known store

**Price utilities:**
- `_parse_price(raw: str) -> float | None` — strips currency symbols, removes thousand separators, handles `,` and `.` as decimal
- Amazon price: concatenates `a-price-whole` + `a-price-fraction` before `_parse_price()`

**Migration:** Add `scraper_type: str | None` column to `WatchItem` (nullable; `None` = auto-detect via extraction hierarchy). New Alembic migration in this issue.

- Scraper returns `ScraperResult(price=None, status="error")` on any exception — caller logs warning, skips `PriceHistory` write, does not crash
- Scraper returns `ScraperResult(price=None, status="oos")` when item detected as out of stock — caller logs info, skips `PriceHistory` write

### Acceptance criteria

- [x] `RetailerRouter` routes `amazon.ca` → `AmazonCAScraper`; unknown domain → `HTTPScraper` with `PatchrightScraper` fallback on `status="error"`
- [x] `AmazonCAScraper.get_price()` returns `ScraperResult(price=float, status="ok")` for a live Amazon.ca product URL
- [x] `HTTPScraper.get_price()` extracts price via schema.org JSON-LD for a live BestBuy.ca product URL
- [x] `HTTPScraper.get_price()` extracts price via Shopify API for a live deadstock.ca product URL
- [x] `HTTPScraper.get_price()` extracts price via `__NEXT_DATA__` heuristic for a live SSENSE product URL
- [x] `PatchrightScraper.get_price()` extracts price on a JS-rendered URL where `HTTPScraper` returns `status="error"`
- [x] OOS item detected via schema.org or Shopify `available` field returns `ScraperResult(price=None, status="oos")`
- [x] Any scraper returns `ScraperResult(price=None, status="error")` on connection error without raising
- [x] `_parse_price("$1,299.99 CAD")` returns `1299.99`
- [x] Patchright browser instance is shared within a job run and closed after
- [x] New Alembic migration adds `watch_items.scraper_type` nullable column

---

## [✅] Issue #4 — Stock Price Service (Finnhub WebSocket + REST)

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #1, #2

### What to build

`FinnhubClient` class that maintains a persistent WebSocket connection for real-time threshold detection. Finnhub REST used for ticker validation and one-off price queries. yfinance used only for dashboard price history charts.

- `services/stocks.py`: `FinnhubClient` class
  - `async def start()` / `async def stop()` — lifecycle, called from FastAPI lifespan; subscribes all active `StockAlert` tickers on start
  - `async def subscribe(ticker: str)` / `async def unsubscribe(ticker: str)` — called from API routes when a `StockAlert` is created, paused, or deleted
  - On each WebSocket price tick: check all active `StockAlert` thresholds; if crossed and `alert.alerted_at is None` → INSERT `Event { type: "STOCK_THRESHOLD" }` + `event_queue.put_nowait(event)` + set `alert.alerted_at = now()`; if price recovers above target → clear `alert.alerted_at` (re-arm)
  - Exponential backoff on disconnect; re-subscribes all active tickers on reconnect
  - `async def get_price(ticker: str) -> float | None` — Finnhub REST `/api/v1/quote?symbol={ticker}` via httpx; used for one-off queries (manual poll trigger, validation)
  - `async def validate_ticker(ticker: str) -> bool` — calls `get_price()`; returns `True` if result is non-null and non-zero
  - `async def get_price_history(ticker: str, period: str = "1mo") -> list[dict]` — yfinance `Ticker.history(period=period)` for dashboard price history charts
- `FINNHUB_API_KEY` from `settings.finnhub_api_key`; if unset → client disabled gracefully, no crash
- `get_price()` returns `None` on any exception — caller logs error, skips alert

### Acceptance criteria

- [x] `FinnhubClient.start()` connects to Finnhub WebSocket and subscribes all active `StockAlert` tickers
- [x] Price tick crossing a `StockAlert` threshold produces a `STOCK_THRESHOLD` event and sets `alerted_at`
- [x] Second tick with price still crossing threshold does not produce a second event (`alerted_at` blocks re-trigger)
- [x] Price recovering above target clears `alerted_at`; next crossing produces a new event (re-arm)
- [x] WebSocket disconnect triggers exponential backoff reconnect; re-subscribes all active tickers on reconnect
- [x] `validate_ticker("AAPL")` returns `True` via Finnhub REST
- [x] `validate_ticker("INVALID_XYZ")` returns `False`
- [x] `get_price("AAPL")` returns a non-null float via Finnhub REST
- [x] `FINNHUB_API_KEY` unset → client disabled, `get_price()` returns `None`, no crash
- [x] `get_price_history("AAPL", "1mo")` returns list of price points via yfinance

### Note

`#19` (2026-08-02) extends `subscribe()`/`unsubscribe()` to also cover `Position` tickers, not just `StockAlert` — see `#19` for the shared-subscription accounting this requires (a ticker referenced by both must not be unsubscribed while either still needs it). Superseded by `#19`'s 2026-08-10 revision — `Position` no longer subscribes at all; see that issue.

**Extension (2026-08-12) — live per-tick price cache, not yet built.** Today, `_check_threshold` (`stocks.py:178`) only persists a price at the instant a threshold *crosses* (`_fire_event` writes `StockAlert.last_price`, `stocks.py:222`) — every other tick is checked and discarded, so `last_price` is stale between crossings, not a live price (full trace: `#19`'s "Correction" note, `architecture.md`'s matching callout). Proposed fix, scoped to this issue since it's `_check_threshold`'s own code:

- Add an in-memory `{ticker: price}` dict on `FinnhubClient` (same shape/pattern as `_cache`, `stocks.py:37`), overwritten — not appended to — on every tick for every WS-subscribed ticker, regardless of whether it crosses. One dict slot per ticker; update cost is flat (a single key overwrite) no matter how many ticks/sec a ticker gets, so tick volume alone isn't a reason to avoid this.
- **No DB write added.** `StockAlert.last_price`'s existing crossing-only semantics stay untouched (still correct for audit/notification history) — the new live value lives purely in memory, read directly by `GET /api/stockalerts`/`GET /api/positions` at request time instead of falling back to the stale DB column.
- Does **not** on its own fix `#37`'s broadcast — that stream still needs its own throttling regardless of how fresh the underlying cache is (`#37`'s existing scope note, `issues.md:1018`); this only makes the *value being read* live, a separate concern from *how often it's pushed to the frontend*.
- Unblocks: `#19`'s `GET /api/positions` enrichment (would read this cache instead of the stale DB column for alert-backed tickers), and gives `#37` something genuinely live to broadcast once that issue adds its own throttle.

---

## [✅] Issue #5 — Notification Service (Pushover + Email)

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #1, #2

### What to build

Full notification dispatch: Pushover HTTP sender, Gmail SMTP sender, and a single `send_alert()` entry point. Both channels run independently — email failure does not block Pushover.

**Pushover sender:**
- Load `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` from env at startup via `pydantic-settings`
- `async def send_pushover(title, body, url=None)` — HTTP POST to `https://api.pushover.net/1/messages.json` via httpx
- Optional `url` + `url_title = "View"` fields included when URL is provided
- One call delivers to all registered Pushover devices (iPhone, iPad, Mac, Apple Watch) simultaneously

**Email sender:**
- `smtplib` STARTTLS to `smtp.gmail.com:587`
- Gmail App Password from `GMAIL_APP_PASSWORD` env var
- HTML email body: item name, current price, target price, direct product/ticker link

**Entry point:**
- `async def send_alert(title, body, url=None)` — calls `send_pushover` then `send_email`; each wrapped in try/except so one failure doesn't block the other

### Acceptance criteria

- [x] `send_alert()` sends Pushover push to all registered devices via single HTTP POST
- [x] `send_alert()` sends email to configured Gmail address
- [x] Email body contains item name, current price, target price, URL
- [x] Pushover failure does not prevent email from sending (and vice versa)
- [x] `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` loaded from `.env` — never hardcoded

---

## Group 2 — Scheduling + Event Queue

---

## [✅] Issue #6 — APScheduler Jobs + Event Queue Writes

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #2, #3, #4

### What to build

Wire APScheduler into FastAPI lifespan and implement the two polling jobs. Jobs write `Event` rows on threshold crossing and enqueue them — they never call notification or analysis code directly.

**Price poll job (every 6 hours):**
- Query all active `WatchItem`s
- For each: call `RetailerRouter.get_price(url, scraper_type=item.scraper_type)` → `ScraperResult`
- Write `PriceHistory` row only on `result.status == "ok"`
- If `result.price <= item.target_price` AND `item.alerted_at is None`:
  - INSERT `Event { type: "PRICE_DROP", payload: { watch_item_id, price, url }, status: "pending" }`
  - `event_queue.put_nowait(event)` — zero-latency delivery to consumers
  - Set `item.alerted_at = now()`
- If `current_price > item.target_price`: clear `item.alerted_at` (re-arm)
- Update `item.last_price`
- On `result.status == "oos"`: log info (item out of stock), skip `PriceHistory` write, continue
- On `result.status == "error"`: log warning, skip `PriceHistory` write, continue

**Scheduler wiring:**
- `AsyncIOScheduler` started in FastAPI `lifespan` context manager
- Price poll job registered with `add_job(..., "interval", hours=6)`
- `FinnhubClient.start()` called in lifespan alongside scheduler startup; `FinnhubClient.stop()` on shutdown
- `event_queue: asyncio.Queue` created at startup and passed to price poll job, `FinnhubClient`, and consumers
- Manual trigger function exposed for `POST /api/poll/prices` endpoint

### Acceptance criteria

- [x] Price poll job runs every 6 hours
- [x] Each poll cycle writes a `PriceHistory` row for every successfully scraped item
- [x] `PRICE_DROP` event written when `current_price <= target_price` and `alerted_at` is None
- [x] No second `PRICE_DROP` event written on next poll if price still below target (`alerted_at` blocks re-trigger)
- [x] `alerted_at` cleared when price recovers above target (re-arm confirmed on subsequent drop)
- [x] Scraper returning `None` logs warning and continues without crashing scheduler
- [x] Scheduler starts on FastAPI startup and shuts down on shutdown
- [x] `FinnhubClient` started in lifespan and receives the shared `event_queue`

### Implementation notes

- Queue holds `event.id` (int), not the ORM object. Consumers re-fetch by ID in a fresh session.
- `_process_item` holds the DB session open across the full scraper call (including Playwright, 5–30s). Safe for sequential single-server scraping. **Refactor to read→close→scrape→open→write before adding any concurrency** (e.g. semaphore-limited parallel scraping in a future issue).
- `POST /api/poll/prices` has no auth (Issue #8) and no concurrency guard — hitting it while the scheduler job is running starts two concurrent scrape cycles.

---

## [✅] Issue #7 — Event Consumers (Notify + Analysis Stub)

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #5, #6

### What to build

Two independent consumers listening on a shared `asyncio.Queue`. Each dequeues events, processes them, and marks them `processed` or `failed`. On startup, any `status="pending"` DB rows are loaded into the queue (crash recovery). This issue implements `NotifyConsumer` fully and `AnalysisConsumer` as a stub (wired in #9).

**Startup (FastAPI lifespan):**
- Create `event_queue: asyncio.Queue` and pass it to both jobs (#6) and both consumers
- Load all `Event` rows WHERE `status = "pending"` from DB into queue (crash recovery)
- Start `NotifyConsumer` and `AnalysisConsumer` as `asyncio.Task`s via `asyncio.create_task()`

**NotifyConsumer:**
- `async def run(queue: asyncio.Queue)` — `while True: event = await queue.get()`
- Call `send_alert(title, body, url)` with content derived from `event.payload`
- On success: update `event.status = "processed"`, `event.processed_at = now()`
- On failure: update `event.status = "failed"`
- Works for both `PRICE_DROP` and `STOCK_THRESHOLD` event types
- `queue.task_done()` after each event regardless of outcome

**AnalysisConsumer (stub):**
- `async def run(queue: asyncio.Queue)` — separate task, reads from same queue
- Filters to `type = "STOCK_THRESHOLD"` events only; passes others back via re-enqueue or ignores
- Check `stock_alert.run_analysis` — if False, skip silently
- If True: create `AnalysisResult { status: "pending" }` row (TradingAgents wiring deferred to #9)
- Fully wired in #9

### Implementation notes

- Single dispatcher task (`consumers/dispatcher.py`) dequeues `event_id`, fetches Event by ID in a fresh session, routes to `notify.handle()` then `analysis.handle()`.
- Notification fires **immediately** on threshold crossing. Follow-up notification after TradingAgents completes is Issue #9's scope.
- `send_alert()` is best-effort (fire-and-forget). `status="failed"` covers data errors only (WatchItem/StockAlert not found). Delivery failures are logged per-channel with specific error type.
- Analysis stub failure (e.g. DB error writing AnalysisResult) does not prevent event being marked `processed` — logged and skipped.
- Crash recovery: all `status="pending"` Event IDs loaded into queue on lifespan startup before dispatcher starts.

### Acceptance criteria

- [x] `NotifyConsumer` sends Pushover + email for a `PRICE_DROP` event and marks it `processed`
- [x] `NotifyConsumer` sends Pushover + email for a `STOCK_THRESHOLD` event and marks it `processed`
- [x] Failed notification marks event `failed`, does not crash consumer loop
- [x] `AnalysisConsumer` stub creates `AnalysisResult { status: "pending" }` when `run_analysis = True`
- [x] `AnalysisConsumer` skips silently when `run_analysis = False`
- [x] On startup with a pending event in DB, consumer processes it without a new poll cycle (crash recovery)
- [x] Two events produced in quick succession are both processed without delay (queue, not poll interval)

---

## [ ] Issue #18 — DB Connection Resilience (pool_pre_ping + Pending-Event Rescan)

**Type:** feat / AFK
**Estimate:** ~1.5h
**Blocked by:** #6, #7

### What to build

- **`backend/app/core/db.py`**: add `pool_pre_ping=True` to `create_async_engine(...)` — SQLAlchemy pings each pooled connection before handing it out, transparently discarding and replacing a stale one instead of surfacing a connection error to the caller.
- **New scheduled job** (APScheduler, alongside the existing 6h price-poll job in `scheduler/jobs.py`): periodically (every 5–10 min) queries `Event WHERE status = 'pending' AND created_at < now() - <grace_period>` and re-enqueues matching event IDs onto the shared `asyncio.Queue` — same mechanism the lifespan startup crash-recovery already runs once at boot.
- Grace period should be generous enough that an event still legitimately mid-dispatch isn't re-queued concurrently. Dispatch is normally near-instant (single sequential dispatcher, no concurrent processing), so a few minutes is safe.

### Why (context)

Observed gap while debugging a real local network outage (2026-07-02). The app currently only recovers "stuck pending" events at process startup (`lifespan`'s one-time `WHERE status='pending'` reload into the queue). If `dispatcher._dispatch()` fails mid-processing because the DB was transiently unreachable (e.g. a NAS outage), the event is dropped from the in-memory queue (`queue.task_done()` still runs in the `finally` block) but stays at `status='pending'` in the DB — nothing re-queues it until the container is manually restarted. The same gap indirectly affects `services/trading_agents.py::run_analysis`'s catch-all failure handling (#9) — that write itself needs DB connectivity to record `status='failed'`.

Separately: `core/db.py`'s engine has no `pool_pre_ping`, so a connection that went stale during an outage can produce one avoidable failed query before the pool replaces it.

### Acceptance criteria

- [ ] `pool_pre_ping=True` set on the async engine
- [ ] New scheduled job re-queues events stuck at `status='pending'` past the grace period, without requiring an app restart
- [ ] An event actively being dispatched (not yet stuck) is not re-queued concurrently by the rescan job
- [ ] Manual test: simulate a DB outage mid-dispatch (e.g. temporarily block the NAS connection), confirm the event is picked up and processed once connectivity returns and the next rescan cycle runs, without a restart
- [ ] `GET /api/health` and existing event-processing behavior unaffected when no events are stuck

---

## Group 3 — API

---

## [✅] Issue #8 — FastAPI Routes + Auth

**Type:** feat / AFK
**Estimate:** ~4h
**Blocked by:** #2, #3, #4, #5, #7

### What to build

All API routes, shared API key auth, CORS, and rate limiting on manual poll triggers.

**Auth:**
- `core/auth.py`: `verify_api_key` dependency — reads `X-API-Key` header, compares to `settings.api_key`, raises 401 on mismatch
- Applied via `dependencies=[Depends(verify_api_key)]` at router-mount time — no per-route decoration
- `GET /api/health` exempt from auth

**Routers:**
- `api/items.py`: GET, POST, PATCH, DELETE `/api/items`, GET `/api/items/{id}/history?days=30`
- `api/stock_alerts.py`: GET, POST, PATCH, DELETE `/api/stockalerts`
- `api/poll.py`: POST `/api/poll/prices`, POST `/api/poll/stocks` — rate-limited to 1 call per 5 minutes each (in-memory timestamp)
- `api/health.py`: GET `/api/health` → `{ status: "ok" }` — no auth

**Details:**
- POST `/api/items` derives `retailer` from URL domain and probes URL via extraction hierarchy to set `WatchItem.scraper_type` (stored for poll-time use); optional `scraper_type` field in request body overrides auto-detection
- POST `/api/stockalerts` validates ticker via `validate_ticker()` before saving — returns 400 if invalid
- CORS origins from `CORS_ORIGINS` env var (comma-separated)
- No subscriptions routes — Pushover uses static env vars, no per-device registration needed

### Acceptance criteria

- [x] All routes return 401 when `X-API-Key` header is missing or wrong
- [x] `GET /api/health` returns 200 with no auth header required
- [x] `POST /api/items` with `amazon.ca` URL sets `retailer = "amazon_ca"` automatically
- [x] `POST /api/items` with a Shopify URL sets `scraper_type = null` (detected at create-time via extraction hierarchy; stored on `WatchItem`, not exposed in the API response — see `.doc/api.md`)
- [x] `POST /api/items` with explicit `scraper_type = "patchright"` in body stores that value, skipping auto-detection
- [x] `POST /api/stockalerts` with `ticker = "INVALID_XYZ"` returns 400
- [x] `POST /api/poll/prices` called twice within 5 minutes — second call rejected
- [x] DELETE `/api/items/{id}` cascades and removes all `PriceHistory` rows
- [x] CORS allows requests from origin in `CORS_ORIGINS` env var

---

## Group 4 — AI Analysis

---

## [✅] Issue #9 — TradingAgents Integration

**Type:** feat / AFK
**Estimate:** ~5h
**Blocked by:** #7, #8

### What to build

Wire TradingAgents subprocess into `AnalysisConsumer` and expose manual trigger endpoint.

**`services/trading_agents.py`:**
- `async def run_analysis(ticker: str, result_id: int) -> dict | None`
- Spawns `python run.py --ticker {ticker}` via `asyncio.create_subprocess_exec` in `/opt/tradingagents`
- Captures stdout, parses structured JSON output
- Updates `AnalysisResult { status: "running" }` on spawn, `{ status: "done", result: {...} }` on success, `{ status: "failed" }` on non-zero exit or timeout (30-min max)

**AnalysisConsumer (full wiring, replacing stub from #7):**
- On `STOCK_THRESHOLD` event where `stock_alert.run_analysis = True`:
  - Create `AnalysisResult { status: "pending" }`
  - Spawn `run_analysis()` as async task
  - On completion: call `send_alert()` with analysis summary as follow-up push

**`POST /api/stockalerts/{id}/analyze`:**
- Manual trigger — ignores `run_analysis` flag, always runs
- Returns 409 if `AnalysisResult` with `status IN ("pending", "running")` already exists for this ticker
- Creates `AnalysisResult { status: "pending" }` and returns immediately

**`GET /api/stockalerts/{id}/analysis`:**
- Returns list of `AnalysisResult` for this stock alert, ordered by `created_at` desc
- Query param: `?limit=10` (default 10)

**TradingAgents installation (Pi host, not inside Docker):**
- Cloned at `/opt/tradingagents` on Pi host; mounted into backend container via `docker-compose.yml` volume: `/opt/tradingagents:/opt/tradingagents`
- Not a submodule — managed independently; version tracked by commit hash

**`GET /api/analysis/tradingagents/version`:**
- Runs `git fetch origin` then `git rev-list HEAD..origin/main --count` in `/opt/tradingagents`
- Returns `{ current_commit, current_date, latest_commit, latest_date, behind_count, update_available: bool }`
- Returns `{ available: false }` if `/opt/tradingagents` not cloned yet

**`POST /api/analysis/tradingagents/update`:**
- Runs `git pull` in `/opt/tradingagents` via `asyncio.create_subprocess_exec`
- Returns `{ success: bool, new_commit, output }` (stdout/stderr from git)
- Protected by API key auth (same as all other routes)
- Note: trusts upstream `tauricresearch/tradingagents` — only call when update is expected

### Acceptance criteria

- [x] `POST /api/stockalerts/{id}/analyze` returns 202 immediately; `AnalysisResult.status` transitions `pending → running → done`
- [x] `POST /api/stockalerts/{id}/analyze` returns 409 if analysis already running
- [x] `GET /api/stockalerts/{id}/analysis` returns completed results with non-null `result` JSON
- [x] `AnalysisConsumer` creates and runs analysis when `run_analysis = True` on a `STOCK_THRESHOLD` event
- [x] `AnalysisConsumer` skips silently when `run_analysis = False`
- [x] Follow-up Pushover push sent on analysis completion (separate from the immediate threshold alert fired in #7)
- [x] TradingAgents subprocess timeout of 30 minutes — sets `status = "failed"` on timeout
- [x] `/opt/tradingagents` path missing → `status = "failed"` with error logged, no crash
- [x] `GET /api/analysis/tradingagents/version` returns correct `behind_count` and `update_available`
- [x] `POST /api/analysis/tradingagents/update` runs `git pull` and returns new commit hash

---

## [x] Issue #17 — TradingAgents Progress Heartbeat + Idle Timeout

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #9

### What to build

Replace #9's flat 30-minute total-runtime timeout with an idle-timeout driven by real progress signal from the running subprocess, and expose that progress via the API.

- **`backend/scripts/run_tradingagents.py`**: custom LangChain callback handler (same shape as upstream's `cli/stats_handler.py::StatsCallbackHandler`), passed via `TradingAgentsGraph(..., callbacks=[handler])`. On `on_llm_start` / `on_chat_model_start` / `on_tool_start`, prints one heartbeat line to **stderr** (e.g. `HEARTBEAT llm_calls=N tokens_in=X tokens_out=Y`) — stdout stays reserved for the single final JSON line, must not be polluted.
- **`backend/app/services/trading_agents.py::run_analysis()`**: stop using `asyncio.wait_for(process.communicate(), timeout=...)` (blocks until exit, no visibility until the end). Instead, read `process.stderr` incrementally (`asyncio.StreamReader.readline()` loop) while the process runs. Each heartbeat line resets an **idle timer**; kill the process only after N minutes with *no* heartbeat, not after a fixed total elapsed time regardless of activity.
- **`AnalysisResult`**: new fields for live progress (`llm_calls`, `tokens_in`, `tokens_out`, `last_heartbeat_at` — plain columns or a `progress` JSON blob) updated on each heartbeat, so `GET /api/stockalerts/{id}/analysis` shows real activity while `status="running"` instead of a flat, undifferentiated "running".
- **`AnalysisResult`**: new `error_reason` field (`"idle_timeout"` / `"subprocess_error"` / `"invalid_output"`) so failures are distinguishable via the API instead of a bare `status="failed"` with no detail (currently only visible in server logs).

### Why (context)

#9 ships with `_TIMEOUT_SECONDS = 30 * 60`, flat, regardless of the alert's own config. A deep/high-effort run (`max_debate_rounds=5`, `max_risk_discuss_rounds=5`, `anthropic_effort="high"`, all 4 analysts) does many more LLM calls than a shallow one and can legitimately approach or exceed 30 minutes — observed ~20 minutes / 24 LLM calls for a single **medium**-effort manual CLI run with `max_debate_rounds=5`. A flat timeout risks killing legitimately-still-working deep runs as false-positive hangs, while wasting most of the budget on shallow ones that finish in a few minutes.

Investigated whether `TradingAgentsGraph` exposes per-agent progress (the CLI's live "Team/Agent/Status" table) through its public API: it doesn't. `callbacks` is wired only into the LLM client (`llm_kwargs["callbacks"] = self.callbacks` in `trading_graph.py`), giving per-LLM-call granularity (call count, token usage, timing) — not per-agent. The richer per-agent view only exists internally via the `debug=True` constructor flag, which streams `self.graph.stream(...)` but also calls `msg.pretty_print()` straight to stdout for the CLI's own display — incompatible with our subprocess's clean-stdout-JSON contract. LLM-call-level heartbeat is what's actually available and is sufficient: it directly proves forward progress without needing per-agent detail.

### Acceptance criteria

- [x] Heartbeat lines appear on stderr during a real run, one per LLM/tool call start
- [x] Idle timer resets on each heartbeat; process is only killed after N minutes of no heartbeat, not flat total elapsed time
- [x] A run that legitimately takes 25+ minutes with continuous heartbeats completes successfully (not killed)
- [x] A genuinely hung subprocess (no heartbeats) is killed within the idle-timeout window
- [x] `AnalysisResult` exposes live progress (`llm_calls`, tokens, `last_heartbeat_at`) while `status="running"`
- [x] `AnalysisResult` failure states are distinguishable (idle-timeout vs subprocess error vs bad JSON output) via `error_reason`, not just `status="failed"`

---

## [x] Issue #24 — Wishlist Product/Listing Model (Multi-Retailer Grouping)

**Type:** feat / AFK
**Estimate:** ~6h
**Blocked by:** #8

### What to build

Splits the flat `WatchItem` model into `Product` (the thing being tracked, one shared target price) + `WatchItem`-as-listing (one retailer's URL/price for that product), so the wishlist can show one row per product with multiple retailer listings grouped underneath — instead of one row per URL.

**Model:**
- New `Product` table: `id, name, target_price, alerted_at, created_at`
- `WatchItem` loses `target_price`/`alerted_at`, gains `product_id` (FK, not null) — becomes purely a listing record: `retailer, url, last_price, product_id`

**Migration — two-phase (expand, then contract later), not one big-bang change:**
- **Migration A (expand):** create `products`; add nullable `product_id` to `watch_items`; backfill by reusing each existing `watch_items.id` directly as the new `products.id` (every pre-existing row becomes a "product of one," trivial 1:1 correlation, no data loss); reset the `products` id sequence past the reused values; set `product_id` `NOT NULL` + add the FK constraint. Old `target_price`/`alerted_at` columns stay on `watch_items`, unused but untouched — reversible if something's wrong.
- **Migration B (contract, separate/later):** drop `watch_items.target_price` and `watch_items.alerted_at`, only once the app's fully verified against the new model. Not bundled into this issue's completion.
- Take an explicit `pg_dump` snapshot before running Migration A — first migration in this repo that transforms existing data rather than just altering schema, on live Pi/NAS-hosted Postgres.

**API changes (`app/api/items.py`):**
- `GET /api/items` — returns `Product`s, each with nested `listings: WatchItem[]`, instead of a flat list
- `POST /api/items` — either creates a new `Product` + its first listing, or attaches a new listing to an existing `product_id`
- Editing target price operates on the `Product`, applies to all its listings
- Pause/delete operate at the listing level (open question: should "pause" also have a product-wide option? not decided yet)
- **`POST /api/items` does not scrape synchronously.** URL validation on add is syntax-only (`new URL()` client-side) — no live-scrape/liveness check against the retailer at add time. A new listing is created in a pending/unresolved state and picked up by the next regularly-scheduled poll cycle, same as any other listing. Deliberate: a synchronous scrape on add would mean spinning up `PatchrightScraper` (headless Chromium) on the Pi purely because a user typed a URL, and repeated on-demand hits to the same retailer URL while a user is still composing the add-item form risk tripping the exact bot detection `scraping.md`'s `PatchrightScraper` mitigations exist to avoid. A `None` result on the first poll is already a normal, tolerated outcome in this system (`scraping.md`: logged as a warning, `PriceHistory` write skipped, scheduler doesn't crash) — no new failure-handling path is needed for "the retailer didn't resolve immediately."

**Alerting logic changes (scheduler/dispatcher):**
- On any listing's scrape completing, recompute `min(last_price across that product's active listings)` and compare to `Product.target_price` — not that one listing's own price in isolation
- Alert fires when *any* listing's price reaches the target (mathematically equivalent to "the cheapest listing crosses it")
- Dedup (`alerted_at`) moves to `Product` — one alert per crossing regardless of which listing triggered it; re-arms (clears `alerted_at`) when price recovers above target, mirroring the existing `StockAlert` pattern

### Why (context)

Reverses `PRD.md`'s stated "Out of Scope: Price comparison across multiple retailers for the same product" — a deliberate scope change made while designing #10.1's wishlist table, not an oversight. Surfaced because the UI was being designed around one row per product (e.g. "Apple AirPods Max 2" showing both Costco and BestBuy listings, one shared target), which the flat `WatchItem` model has no way to represent. `PRD.md` needs updating to match once this ships.

Blocks the entire #10.1–#10.5 chain — their original scoping assumed "backend already ready, zero backend work needed," which was true for the flat model and is no longer true for the grouped one.

### Shipped (2026-08-03)

Full plan/design record in `.plan/24-wishlist-product-listing-model/`. Two deviations from the original scope worth noting:

- **`pg_dump` snapshot skipped** — turned out moot: the NAS `watch_items` table was empty pre-migration (nothing had ever written a real item through the API yet), so there was no existing data at risk. Verified the backfill instead via row-count equality and an `information_schema.columns` check against the real NAS DB.
- **Migration `0010` added post-review**, on top of the original Migration A (`0009`): the initial FK on `watch_items.product_id` was missing `ondelete="CASCADE"` (unlike the established `price_history.watch_item_id` pattern) — a code-review finding, fixed with a follow-up migration since `0009` was already applied.

Also added, beyond the original issue text: `Listing.last_scrape_status` (`ok`/`oos`/`error`, tracked per poll) and a separate `POST /api/items/{product_id}/listings` endpoint rather than one polymorphic `POST /api/items` — both surfaced during a grill-me design pass, see the plan's `context.md` for the reasoning.

### Acceptance criteria

- [x] Migration A creates `products` + `product_id` FK on `watch_items`, backfills every existing row as a product-of-one, preserves all existing data (verified against a `pg_dump` snapshot — see deviation note above)
- [x] `GET /api/items` returns products with nested `listings[]`
- [x] `POST /api/items` supports both "new product" and "add listing to existing product"
- [x] Editing a product's target price is reflected in alerting for all its listings
- [x] Price-drop detection compares the cheapest active listing's price against `Product.target_price`, not per-listing
- [x] Alert dedup/re-arm (`alerted_at`) lives on `Product`, fires once per crossing regardless of which listing triggered it
- [x] Migration B (dropping the old `watch_items` columns) tracked as a separate follow-up issue, not required for this one to close

---

## Group 5 — Frontend

---

## [🔀] Issue #10.1 — ~~Wishlist Page (Read-Only)~~ — MERGED into #36

**Merged 2026-08-03** — folded into `#36 — Wishlist Page (Real Data + Live Price History via SSE)` alongside `#10.3`, while planning the real-data wiring for `frontend/src/app/watchlist/page.tsx`. Decided during that planning conversation to skip short-polling in favor of SSE push, which pulled price-history wiring in at the same time — see `#36` for the current scope. Body below kept for history, not an active issue.

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #8, #24

### What to build

`/wishlist` page — table of `WatchItem`s against the already-built backend (`GET /api/items`), proxied through the existing `app/api/proxy/[...path]/route.ts` (no new proxy work needed). Columns: name, retailer, current price, target price, `StatusBadge` (green below target / yellow at target / grey above target), last checked. SWR polling, 30-second refresh. Includes only the typed fetch helper this slice needs (e.g. `getItems()`) — not a full upfront API client; later slices add their own typed calls as needed.

### Why (context)

Split out of the original single "Issue #10 — Next.js Dashboard" (~8h) into five vertical slices — each a complete, independently demoable/mergeable path through client code + UI against the already-ready backend, rather than one large horizontal build. This slice specifically sets the visual/data pattern (table, `StatusBadge`, SWR polling) that #10.4 (stocks page) reuses. Also the first slice to close the gap where #22 (Overview Dashboard) shipped its bentobox shell ahead of its own listed blockers, including this one.

**Shipped ahead of its blockers (2026-07-28), same pattern as #22's bentobox:** `frontend/src/app/watchlist/page.tsx` exists and covers most of this slice's UI plus a chunk of #10.2/#10.3 — table (search, sort by date added), price sparkline, a side panel with inline edit for name/target price/listings, and a "New Item" dialog. All of it runs against a hardcoded mock `products` array, not `GET /api/items` — no SWR polling, no real mutations (every write path is a `console.log` stub). It also already reflects #24's grouped Product/Listing model rather than this issue's original flat-`WatchItem` description above, so that description is stale and should be rewritten once #24 actually ships, rather than trusted as the current design. None of this issue's acceptance criteria are met yet; do not mark it done until the page is wired to the real backend.

### Acceptance criteria

- [ ] `/wishlist` displays all `WatchItem`s with correct price and status badge
- [ ] Table auto-refreshes every 30 seconds
- [ ] `X-API-Key` header never appears in browser network tab (proxy confirmed)

---

## [x] Issue #10.2 — Wishlist Mutations (Add / Edit / Pause / Delete)

**Type:** feat / AFK
**Estimate:** ~2h → revised to ~6.5h during planning (see `.plan/10.2-wishlist-mutations/_index.md`) — the backend contract this issue depends on turned out not to be as "already-built" as originally assumed; see below.
**Blocked by:** #36 (formerly #10.1, merged into #36)

### What to build

Add-item form (name + target price + N retailer URLs) and per-row/per-listing actions (edit target, pause/resume, delete) on `/wishlist`.

**Correction to this issue's original framing:** the line below used to read "against the already-built `POST`/`PATCH`/`DELETE /api/items` routes" — planning for this issue found that framing wrong on two counts, both resolved by extending those routes rather than treating them as fixed:
- `ListingUpdate` (`PATCH /api/items/{id}/listings/{id}`) only supported `active` (pause/resume) — no way to edit a listing's URL. Added `url`/`retailer`, preserving the listing's `id` and price history (rejected delete+recreate, which would've silently wiped history).
- `ProductCreate` (`POST /api/items`) only supported one URL, created atomically with the product. Reworked twice during planning (chained per-URL frontend calls → same chain moved to a background loop → settled on **one bulk request**: `{name, target_price, urls: string[]}`, backend dedups + checks existing URLs + probes survivors **concurrently** (bounded, `asyncio.Semaphore(3)`) + returns `{product, failed: [{url, detail}]}`). This is the first place this codebase drives the scraper concurrently — verified safe against `PatchrightScraper`'s shared browser-context design before building it; capped anyway since the scheduler's own scrape loop runs sequentially and the Pi 5 8GB runs the whole stack. Full design history in `.plan/10.2-wishlist-mutations/challenges.md`.

Pause/resume also moved from a row-level (product) action to a **per-listing** toggle in the sheet — the backend has no product-level "paused" field (`status` is derived: all listings inactive → `paused`), so a row-level bulk toggle would be ambiguous once individual listings can already be paused.

**Coordination note with `#36`** (surfaced while grilling `#36`'s design, not a design fork of its own): `#36`'s SSE broadcast only fires from the price-scraper (`_process_item`), not from CRUD actions — so a newly-added item won't appear via SSE, it'll appear whenever the *next* scrape cycle happens to run. Each mutation here needs its own `mutate()` immediately after its response resolves — plain await-then-refetch, not optimistic UI (no precedent for that in this codebase, and unnecessary once add-item collapsed to one fast-ish bulk request) — ordinary REST pattern, unrelated to SSE, but worth stating explicitly so it's not assumed SSE will cover it.

**Status (2026-08-07):** Backend done — schema/route changes above, 8 new tests, full suite (274 tests) passing. Frontend wiring (add/edit/pause/delete on `/wishlist`) done — testing skipped, see progress tracker.

### Acceptance criteria

- [x] Add item form (bulk, one request) submits and new item appears in table without full page reload; a partial failure (e.g. one bad URL among several) still creates the product and every successful listing, surfaced via toast
- [x] Edit target price and delete actions update the table without full page reload
- [x] Pause/resume is a per-listing toggle in the item's detail sheet (not a row-level action — see correction above)

---

## [🔀] Issue #10.3 — ~~Price History Chart~~ — MERGED into #36

**Merged 2026-08-03** — folded into `#36` alongside `#10.1`. Body below kept for history, not an active issue.

**Type:** feat / AFK
**Estimate:** ~1.5h
**Blocked by:** #10.1 (not #10.2 — can ship in parallel with it)

### What to build

`PriceHistoryChart` component (recharts `LineChart`), toggled open by clicking a wishlist row, showing the last 30 days of `PriceHistory` data from the already-built `GET /api/items/{id}/history?days=30`.

### Acceptance criteria

- [ ] Clicking a wishlist row expands `PriceHistoryChart` with last 30 days of data

---

## [✅] Issue #36 — Wishlist Page (Real Data + Live Price History via SSE)

**Type:** feat / AFK
**Estimate:** ~6h
**Blocked by:** #8, #24

### Why (context)

Merges former `#10.1` (Wishlist Page, Read-Only) and `#10.3` (Price History Chart) — surfaced while planning the real-data wiring for `frontend/src/app/watchlist/page.tsx` (which already has the full visual shell built against mock data, per `#10.1`'s "shipped ahead of blockers" note below). Two decisions made during that planning conversation pulled the scope together:

1. **Price history has no bulk endpoint** — `GET /api/items/{product_id}/listings/{listing_id}/history` is per-listing, not per-product, so wiring the table sparkline and sheet chart to real data was never going to be a trivial rename regardless of `#10.1` vs `#10.3`'s split — it needed its own fetch design either way. Splitting them into separate issues no longer reflected the real dependency.
2. **SSE over short-polling, deliberately** — rather than `useSWR(..., { refreshInterval: 30000 })` (the pattern used elsewhere in this repo, e.g. `frontend/src/app/page.tsx`), this page adopts Server-Sent Events: the backend pushes on every successful scrape instead of the browser polling for changes. Chosen as a deliberate learning build, not because polling was insufficient for this app's actual 6-hour scrape cadence (it would have been fine) — see `.doc/keynotes.md` → "Layered polling — one loop's output can feed another loop's push" for the full design reasoning.

### What to build

**Frontend — real data, replacing the mock:**
- Delete the hardcoded `products` array (`watchlist/page.tsx:41-169`); fetch `GET /api/proxy/items` instead.
- Rename types to match the real API: `Listing`/`Product` fields become snake_case (`target_price`, `last_price`, `last_checked`, `last_scrape_status`, `active`, `alerted_at`, `product_id`), matching `backend/app/schemas/listing.py:17-28` and `product.py:22-32`. IDs become `number`, not `string` — thread through `openId` state, `Sheet` `key`, dropdown action handlers.
- Delete `stalestCheckedAt()` (page.tsx:173-174) — `status` and `last_checked` are server-computed, use directly.
- Null-guard `bestPrice()` (filter out listings with `last_price: null` before `Math.min`) and `formatLastChecked()` (fallback display when `last_checked: null`) — real listings can be never-scraped.
- Loading and error states for the fetch (mock data could never fail); empty-table state.
- Search/sort logic: rename `createdAt` → `created_at`, otherwise unchanged.

**Frontend — price history (folds in former #10.3):**
- Per-listing history fetch (`GET /api/items/{pid}/listings/{lid}/history?days=30`) via a `useListingHistory(listingId)` hook, called once per listing — table row and sheet each consume it differently, not two separate fetches.
- Table sparkline (`PriceSparkline`): merge all of a product's listings' histories, bucketed by **local calendar day** (raw `checked_at` won't match across listings scraped at different exact times within the same cycle — day-bucket before taking `Math.min` per bucket). Bucketing done **client-side**, via `Date`'s local-timezone-aware methods (e.g. `.toLocaleDateString()`) on the UTC `checked_at` string the backend already sends unchanged — no backend timezone config, no DB changes. Feeds the existing min-across-retailers merge logic in `productPriceHistory()`.
- Sheet chart (`ProductPriceChart`): same local-day-bucketed per-listing data, passed through as-is (component already renders one line per retailer, no changes needed there).

**Backend — SSE push:**
- New broadcast call inside `_process_item` (`jobs.py`), fired **unconditionally** on every successful scrape (every listing, every 6h cycle) — separate from, and in addition to, the existing conditional `Event`/`asyncio.Queue` write used only for alert-crossing (`jobs.py:117-132`, untouched, still feeds Pushover/email exactly as today).
- New route (`GET /api/events/stream` or similar) holding open SSE connections, fed by that broadcast. Lightweight in-memory fan-out, **not** DB-backed like `Event` — a missed push isn't a lost alert, the next reconnect just re-syncs via a normal fetch. **Dedicated to this feature** — `#37`'s eventual stock-tick broadcast gets its own separate endpoint/fan-out, not multiplexed onto this one (their broadcast conditions differ enough — unconditional-per-scrape here vs. throttled-per-tick there — that sharing one connection/schema now would mean designing `#37` prematurely). Payload stays plain unnamed `data: {...}` + `onmessage`, no named `event:` type needed for a single message type.
- Next.js proxy (`frontend/src/app/api/proxy/[...path]/route.ts`) needs a streaming-capable handler — current implementation is one-shot `fetch` → `await res.json()`, GET-only; this needs to relay chunks instead of buffering a single JSON response.

**Frontend — SSE consumption:**
- `EventSource` on the proxied stream URL. On receipt, `mutate()` the relevant SWR keys (`/api/proxy/items` for status/price, the specific listing's history key for the sparkline/chart) — **no** `refreshInterval` polling on this page; SSE is the sole update trigger.
- Because `status` is computed server-side from `alerted_at` (not stored), the same generic per-scrape broadcast covers reflecting an alert-triggered status change in the UI too — no second event type needed.
- **Reconnect recovery**: no `Last-Event-ID` replay is built (deliberate — see broadcast note above, missed pushes aren't buffered). Instead, `es.onopen` (fires on every connect, including reconnects after a drop) triggers one `mutate("/api/proxy/items")` — a plain bulk refetch, same mechanism as any other `useSWR` revalidation, not SSE-specific. This closes the "connected but stale" gap a dropped-then-reconnected tab would otherwise sit in indefinitely (see `.doc/keynotes.md` for the full design discussion).
- **Manual exponential backoff, not native auto-reconnect.** `EventSource`'s built-in reconnect uses a fixed ~3s retry, no escalation — fine for a brief blip, but would hammer the backend every 3s indefinitely during an extended outage. Instead: catch `onerror`, `es.close()`, reopen a fresh `EventSource` on an increasing `setTimeout` delay (1s → 2s → 4s → 8s...), same pattern already used in `services/stocks.py`'s `FinnhubClient._listen()` — real precedent to copy, not a new pattern. Motivation here is consistency/tidiness (own Pi, own network, no third-party rate limit to respect like Finnhub has), not a real resource cost at this app's scale.
- **Connection-status UX, two states, not three.** `onerror` carries no error detail — can't distinguish "backend down" from "network down" from that event alone. Realistic split: (1) **"You're offline"** — driven by `navigator.onLine`/`online`/`offline` window events, reliable, cheap; (2) **"Live updates unavailable"** — catch-all for everything else (backend down, SSE route erroring, routing hiccup), accurate as "something's blocking live updates" without claiming to know the specific cause. A true three-way split (offline / backend-down / other-error) would need a separate health-check ping (e.g. periodic `GET /api/health`) — explicitly out of scope for this issue, revisit only if the two-state version proves insufficient in practice.

> **Known limitation — reconnect recovery is table-only, not history.** The `onopen` refetch above only refreshes `/api/proxy/items` (price/status/last_checked) — it does **not** refresh any listing's price-history key, since `mutate()` only touches the exact key it's given, and SWR has no concept of "related" keys. So if a listing was rescraped *during* a disconnect, its table row corrects immediately on reconnect, but its sparkline/chart stays one data point behind until that listing's *next* real scrape broadcasts normally (via the live `onmessage` path, which does target the correct history key). Accepted as-is: low-stakes (cosmetic, self-healing within one scrape cycle, and the odds of a scrape landing inside a typically-brief disconnect window are already low). Full fix would mean also looping `mutate()` over every history key currently in the SWR cache on `onopen` — more moving parts for a gap that's already minor; revisit only if it proves noticeable in practice.

**Deployment assumption, worth stating explicitly:** this design depends on both the Next.js and FastAPI processes being long-running servers capable of holding a connection open indefinitely — true for this app's actual deployment (Docker Compose on the Pi, persistent containers, `restart: unless-stopped`), but would **break outright** on a serverless host (e.g. Vercel route handlers, AWS Lambda) due to their hard per-request execution time limits. Not a concern for this app's current/planned deployment, but a real compatibility constraint if the frontend's hosting ever changed.

No hard cap needed on concurrent backend SSE connections at this app's scale (single user, at most a handful of open tabs) — not worth engineering around now.

**Explicitly not in scope** (stays `#10.2`): add-item dialog, inline sheet edits, delete/pause actions — all remain `console.log` stubs.

### Acceptance criteria

- [ ] `/watchlist` displays all real `Product`/`Listing` data from `GET /api/items` via the proxy — no mock data remains
- [ ] `X-API-Key` header never appears in browser network tab (proxy confirmed)
- [ ] A listing with `last_price: null` or `last_checked: null` renders a fallback (`—`), not `NaN`/`Invalid Date`
- [ ] Table sparkline shows the min price across a product's retailers, correctly merged by day even when listings were scraped at different times within the same cycle
- [ ] Sheet chart shows one line per retailer, using the same underlying history data as the sparkline
- [ ] Backend emits an SSE push on every successful scrape, regardless of whether price changed
- [ ] Frontend reflects a scrape's result (price, `last_checked`, sparkline point) without a 30-second polling delay — confirmed via network tab, no `refreshInterval` poll firing on this page
- [ ] An alert-crossing scrape still triggers Pushover/email exactly as before (existing `Event`/queue path unaffected by the new broadcast)
- [ ] SSE connection recovers after a browser network drop, via manual reconnect logic (not native auto-reconnect), without a manual page refresh
- [ ] Reconnect attempts back off exponentially (1s → 2s → 4s → 8s...) during an extended outage, not a fixed retry hammering every ~3s
- [ ] After a reconnect, the table (price/status/last_checked) reflects current truth immediately — sparkline lag for listings scraped mid-outage is acceptable, self-corrects on next scrape
- [ ] UI shows a distinct "offline" state when `navigator.onLine` is false, and a separate "live updates unavailable" state for any other sustained connection failure
- [ ] Manual test: rapidly mount/unmount the watchlist page (or toggle React StrictMode) in local dev — backend's SSE fan-out set doesn't grow (no leaked/duplicate connections from the open→close→open double-invoke)

---

## [x] Issue #10.4 — Stock Alert Alarm (Market Detail Sheet)

**Type:** feat / AFK
**Estimate:** ~2h *(revised 2026-08-12 — see rewrite note below)*
**Blocked by:** #36 (was #10.1, merged into #36)

> **Rewritten 2026-08-12 — the text below replaced a stale ticket description.**
> Original text assumed a new `/stocks` route (full table, ticker/last price/
> target/direction/`run_analysis`/status/actions, add form) needed building
> from scratch. Wrong on inspection during planning (`.plan/10.4-stock-alerts/context.md`):
> no such route was ever meant to exist — `/portfolio` already had a compact
> Watchlist tile and `/market/[ticker]` already had a detail page, both shipped
> ahead of this issue. Further corrected mid-implementation: the Watchlist
> tile itself split out into `#10.6` once it became clear it must never
> display `StockAlert` data (config, not market data) and that tile
> membership is the star icon's job, not alert existence. This issue's real
> scope, as actually built: `/market/[ticker]`'s alarm-icon button + two-
> section sheet only (revised again 2026-08-12 from an originally-planned
> `Dialog` container — see `implementation.md`'s Step 3 note). Full history:
> `.plan/10.4-stock-alerts/_index.md`.

### What to build

New alarm-icon button on `/market/[ticker]` (next to the existing star, `#10.6`'s unrelated bookmark toggle), reflecting this ticker's `StockAlert`(s) via a binary fill state (outline = no alerts, filled = any alert exists, active or paused — simplified 2026-08-13, no muted/accent states). `onClick` is constant (always opens the sheet), not a toggle of the same state driving the fill — different interaction shape from the star icon beside it. Click opens a `Sheet` (`side="right"`, same container `watchlist/page.tsx` uses for its product detail panel — not a `Dialog`, see `implementation.md`'s Step 3 note for why) with two independent sections — "Alert when price rises above" / "falls below" — both always showing the same full field set (price, active, `run_analysis`), draft-only until a single sheet-level `Save`/`Cancel` (revised 2026-08-13, supersedes an earlier immediate-commit-per-field design — see `implementation.md`'s Step 3 note; `Save` batches each dirty section into one request, zero requests before it's clicked). Delete stays immediate and separate, its own confirm `Dialog`, not part of the draft. Against the already-built backend (`app/api/stock_alerts.py`'s CRUD routes). No table page, no standalone route — this is entirely a detail-page component. Full spec: `.plan/10.4-stock-alerts/schema.md`, `implementation.md`.

### Acceptance criteria

- [x] Alarm-icon fill state on `/market/[ticker]` is outline when no alerts exist for that ticker, filled when any exist (active or paused) — clicking always opens the sheet regardless of fill state
- [x] Sheet's two sections are draft-only (price/active/`run_analysis` edits produce zero requests) until a single `Save`/`Cancel` pair — `Save` batches each dirty section into one `create`/`update` call, `Cancel` reverts with no request; delete stays immediate and separate via its own nested confirm `Dialog`
- [x] A create request for a direction that already exists for that ticker surfaces the backend's 409 as a toast, not a crash
- [x] `X-API-Key` never appears in browser network tab (generic proxy, unchanged)

---

## [ ] Issue #37 — Stocks/Portfolio Page — Live Updates via SSE (Finnhub Tick Broadcast)

**Type:** feat / AFK
**Estimate:** ~4h
**Blocked by:** #36 (SSE infra must exist), #10.4 (stocks page must exist to update)

### Why (context)

Deferred out of `#36`'s scope deliberately — surfaced while grilling `#36`'s design. `#10.4`'s current acceptance criteria still commit to short-polling (`SWR polling, 30-second refresh`), matching this repo's existing pattern (`page.tsx`'s storage tile). This issue is the follow-up that swaps that polling for the same SSE push mechanism `#36` builds, extended with a second producer.

**Scope note, explicitly not resolved yet** — this is the reason it's a separate issue rather than folded into `#36`: Finnhub ticks arrive far more frequently than the price-scraper's 6h cycle. `#36`'s broadcast is unconditional-per-scrape because scrapes are inherently rare; broadcasting unconditionally per-tick here could flood the SSE connection. Needs its own design pass — likely throttling/debouncing (e.g. max one broadcast per ticker per N seconds) before reusing `#36`'s fan-out mechanism as-is. Revisit design pattern options at that point (see architecture comparison work in `.doc/keynotes.md`'s SSE sections) rather than assuming `#36`'s exact shape transfers unchanged.

### What to build

- `FinnhubClient`'s tick handler (`backend/app/services/stocks.py`) broadcasts to its **own** SSE fan-out set and route (e.g. `GET /api/events/stocks/stream`) — deliberately **not** shared with `#36`'s endpoint (decided while grilling `#36`: their broadcast conditions differ enough — unconditional-per-scrape vs. throttled-per-tick — that a shared connection/schema would mean designing this issue prematurely from within `#36`). A page needing both live streams (e.g. `#22`'s future overview dashboard) opens two `EventSource` connections. Throttled per the note above, mechanism TBD at implementation time.
- Only tickers with an active `StockAlert` are ever websocket-subscribed in the first place (`FinnhubClient`, `stocks.py:37-63` — and per `#19`'s revised design, never extended to `Position`/Holdings either), so this stream structurally can never carry data for a ticker that isn't alert-bearing. Popular Assets, un-alerted Holdings positions, and ad-hoc ticker searches stay on REST `get_price()` + short poll — not in scope for this stream, not a later phase, a permanent boundary (see `.doc/architecture.md` → "Finnhub WebSocket Flow" callout for the full reasoning).
- `/stocks`/`/portfolio` page(s) swap `refreshInterval` polling for `EventSource`, same pattern as `#36`'s wishlist page — scoped to whichever tile(s) actually display alert-bearing tickers; tiles/sections showing only un-alerted tickers keep polling regardless.
- Existing Finnhub → `Event`/queue → Pushover alert path (`STOCK_THRESHOLD`) stays untouched — same "unconditional broadcast, sibling to the existing conditional alert path" split as `#36`.

### Acceptance criteria

- [ ] Stocks/portfolio page reflects a Finnhub tick without a 30-second polling delay, for tickers that have an active `StockAlert`
- [ ] Broadcast frequency is bounded (not one SSE message per raw tick) — specific throttling approach decided during implementation
- [ ] No ticker without an active `StockAlert` ever appears in a broadcast payload — `FinnhubClient.cached_tickers()` is the only source this stream reads from
- [ ] Existing `STOCK_THRESHOLD` → Pushover/email alert path unaffected

---

## [x] Issue #10.5 — Navigation

**Type:** feat / AFK
**Estimate:** ~0.5h
**Blocked by:** #10.1, #10.4

### What to build

Nav bar making `/wishlist` and `/stocks` reachable. `/` itself is superseded by #22 once the overview dashboard ships (becomes the bentobox summary page instead of redirecting to `/wishlist`) — this issue is what makes the two table pages reachable once that happens. Also directly unblocks #22's stuck acceptance criterion requiring both pages stay nav-reachable.

### Acceptance criteria

- [x] `/wishlist` and `/stocks` both reachable via nav from `/` (renamed to `/watchlist` and `/portfolio`)

---

## [ ] Issue #10.6 — Ticker Watchlist (Star, Persisted)

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #10.4

### Why (context)

Surfaced correcting `#10.4` mid-implementation (2026-08-12): `/portfolio`'s Watchlist tile was being built to read `GET /api/stockalerts`, display alert config fields (`target_price`-relative "change%"), and treat "has an active `StockAlert`" as watchlist membership. Wrong on all three counts — confirmed with the user: `/portfolio` should display **market data only** (ticker, type, current price, real % change; shares + purchase month for Holdings), never anything from the `StockAlert` response. Alert config (target price, direction, `run_analysis`) belongs exclusively on `/market/[ticker]`'s alarm-icon sheet — a separate concern from "which tickers am I tracking."

The actual watchlist-membership mechanism already exists in the UI, unwired: the star icon on `/market/[ticker]` (`page.tsx:75,138-143`) — `context.md`'s original `#10.4` planning explicitly scoped it out ("a separate, unrelated concept, not `StockAlert`-backed... stays untouched by this issue"), correctly identifying it as unrelated to alerts, but incorrectly leaving it as decorative local `useState` with no persistence. This issue makes it real: starring a ticker is what populates the Watchlist tile, full stop — no relationship to whether that ticker also happens to have a `StockAlert` or a `Position`.

Reachable identically from all four entry points already established in `#31` (Popular Assets, Holdings, Watchlist, nav search) — same ticker, same star state, regardless of which section you arrived from.

**Naming disambiguation:** "watchlist" is already an overloaded word in this codebase — `/watchlist` (the page) is `#36`'s wishlist `Product`/`Listing` tracker, completely unrelated to stocks. This issue's `/api/watchlist` route and `StarredTicker` model are a third, adjacent use of the word, specifically for `/portfolio`'s Watchlist *tile*. Not a new collision — the tile was already informally called "Watchlist" before this issue; this just gives that name a real backend. Do not confuse `/api/watchlist` with `/api/items` (backs the actual `/watchlist` page).

### What to build

**`StarredTicker` model** (new): `id`, `ticker` (unique), `created_at`. Deliberately minimal — no relationship to `StockAlert` or `Position`, no shared subscription/refcount logic (unlike `#19`'s original mistake with `Position`, this has no Finnhub WS involvement at all — starring a ticker never subscribes anything).

**`app/api/watchlist.py`:**
- `GET /api/watchlist` — list all starred tickers: `[{ id, ticker, created_at }]`
- `POST /api/watchlist` — star a ticker — body `{ ticker }` — validates via Finnhub REST (`validate_ticker()`, same pattern as `POST /api/stockalerts`/`POST /api/positions`) — 400 if invalid, 409 if already starred
- `DELETE /api/watchlist/{id}` — unstar — 204, 404 if not found

**`/market/[ticker]` star icon** — replace the local `useState`/mock-seed (`page.tsx:75`) with `useSWR("/api/proxy/watchlist", fetcher)`, same shared-list-plus-client-filter pattern `#10.4` uses for alerts. Click handler calls `starTicker()`/`unstarTicker()`, then `mutate("/api/proxy/watchlist")` — same mutation convention as every other write in this app.

**`/portfolio`'s Watchlist tile** — reads `GET /api/proxy/watchlist` for the ticker list (membership only — `id`, `ticker`, nothing else renders from this response), then sources every row's price/% change/type from **one** batch call — `GET /api/market/quotes?tickers=AAPL,TSLA,...` (new route, `app/api/market.py` — same file `#30`/`#31` will add) — not `StockAlert.last_price`, and not N separate per-ticker requests. Internally loops the starred tickers through `get_price()` (extended to also capture Finnhub's `dp` field — percent change, already in the REST `/quote` response, currently discarded, only `c` is kept), concurrent + semaphore-bounded (same pattern as `POST /api/items`'s bulk URL probing, `api.md:52`), so the per-ticker TTL cache (`#19`) still applies underneath a single frontend round-trip. Response: `{ quotes: [{ticker, price, change_pct, asset_type}], failed: [{ticker, detail}] }` — `asset_type` (`"stock" | "etf"`) reuses `#30`'s existing field/values (`issues.md`'s `#30` section), **not** a new classification scheme; `name` deliberately omitted — not needed for this row, avoids an extra Finnhub `/stock/profile2` call per ticker that `#30`/`#31` already pay for elsewhere. Response otherwise mirrors `POST /api/items`'s existing partial-failure shape, one bad ticker doesn't fail the whole batch. Category badge is now **real** (`asset_type`), replacing `#10.4`'s hardcoded `"Stock"` — first genuine per-ticker type distinction on this tile (a starred ETF now correctly reads "ETF", not "Stock").

**Supersedes `#10.4`'s Step 2, bullet 2** (`implementation.md`, `stockWatchlistData.map(...)` → `stocks.map(...)`) — that swap should not happen as originally written. See `#10.4`'s own doc for the corrected pointer.

### Acceptance criteria

- [ ] `POST /api/watchlist` stars a ticker, validates via Finnhub REST, 409 on duplicate
- [ ] `DELETE /api/watchlist/{id}` unstars — 204, 404 if not found
- [ ] `GET /api/watchlist` returns all starred tickers
- [ ] Star icon on `/market/[ticker]` persists across reload (reads real data, not local state) — same fill/muted visual treatment already built, now backend-driven
- [ ] Starring a ticker from any of the four entry points (`#31`) reflects identically regardless of which section it was starred from
- [ ] `/portfolio`'s Watchlist tile lists exactly the starred tickers, no more, no fewer — un-starring a ticker removes its row without reload
- [ ] Watchlist tile row displays ticker, **real** category badge (`asset_type` — Stock/ETF, not hardcoded), current price, and **real** % change (Finnhub `dp`) — confirmed not sourced from any `StockAlert` field
- [ ] `GET /api/market/quotes?tickers=...` returns all requested tickers in one call — confirmed via network tab, not N separate requests for N starred tickers
- [ ] A ticker that fails lookup (invalid/unreachable) appears in `failed`, not silently dropped, and doesn't block the rest of the batch
- [ ] A ticker with an active `StockAlert` but not starred does **not** appear in the Watchlist tile; a starred ticker with no `StockAlert` at all appears normally
- [ ] `X-API-Key` never appears in Network tab for any `/api/proxy/watchlist*` request

---

## [ ] Issue #11 — Analysis Results UI

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #9, #10.1–#10.5, #35

### What to build

**Global** analysis history page — every `AnalysisResult` across every ticker, regardless of whether it came from a `StockAlert`'s automatic threshold-crossing or an ad-hoc manual trigger (`#35`) on a ticker with no alert at all. This is the browse-everything log; `#31`'s ticker detail page separately gets its own ticker-scoped section (this ticker's results + a trigger button) — complementary, not duplicated. Plus a TradingAgents version management panel.

- Page backed by `GET /api/analysis` (`#35`, no ticker filter) — list of every `AnalysisResult`, most recent first
- Status badges: `pending` (grey), `running` (blue spinner), `done` (green), `failed` (red)
- Result JSON viewer: collapsible section showing structured TradingAgents output when `status = "done"`
- "Run Analysis" button: calls `POST /api/analysis/{ticker}` (`#35`) — works for any ticker, not gated behind an existing `StockAlert`; disabled + shows 409 message if already running for that ticker
- Auto-refreshes every 10 seconds when any result has `status IN ("pending", "running")`
- Each row links to `/market/{ticker}` (`#31`) rather than a `StockAlert`-id-scoped route, since a row may not have one

**TradingAgents version panel (sidebar or settings section):**
- Calls `GET /api/analysis/tradingagents/version` on page load
- Shows current commit hash + date
- If `update_available: true`: badge "Update available (N commits behind)" + "Update" button
- "Update" button calls `POST /api/analysis/tradingagents/update`; shows spinner while running; displays git output on completion
- If `/opt/tradingagents` not cloned: shows "Not installed" with clone instructions

### Acceptance criteria

- [ ] Global analysis page lists all past results (any ticker, alert-linked or ad-hoc) with correct status badges
- [ ] "Run Analysis" button works on any ticker (via `#35`'s `POST /api/analysis/{ticker}`) and status updates to `running` within one refresh cycle
- [ ] "Run Analysis" button disabled with message when analysis already running for that ticker
- [ ] `done` results show collapsible JSON viewer with TradingAgents output
- [ ] Page auto-refreshes while any result is pending/running; stops refreshing when all are done/failed
- [ ] Version panel shows current commit and "up to date" / "N commits behind" status
- [ ] "Update" button triggers `git pull` and refreshes version panel on completion
- [ ] "Not installed" state shown when `/opt/tradingagents` absent

---

## [ ] Issue #19 — Manual Portfolio Position Tracking

**Type:** feat / AFK
**Estimate:** ~4h
**Blocked by:** #8, #10.1–#10.5

### What to build

Portfolio insights page — holdings, invested amount, current value, unrealized P&L. Positions are entered manually, not synced from a brokerage; user keeps trading directly on Wealthsimple and updates a position here after buying/selling more, the same way `StockAlert` rows are already managed by hand.

**`Position` model** (new): `id`, `ticker`, `shares: float`, `avg_cost: float` (average price paid per share), `notes: str | None`, `created_at`, `updated_at`. One row per ticker (aggregate position, not per-lot) — updated in place when the user buys or trims.

**`app/api/positions.py`:**
- `GET /api/positions` — list all positions, each enriched at read-time with `current_price`: for a ticker with an active `StockAlert`, read `StockAlert.last_price` (see correction under "Live price source" below — this is **not** a live/current price despite the field name, only as fresh as the alert's last threshold crossing); for a ticker with no alert, `current_price` comes from a REST `get_price()` call instead. Also computes `market_value = shares * current_price`, `unrealized_gain = (current_price - avg_cost) * shares`, `unrealized_gain_pct`
- `POST /api/positions` — add position — body `{ ticker, shares, avg_cost, notes? }`, validates ticker via Finnhub REST same as `POST /api/stockalerts`. Does **not** call `FinnhubClient.subscribe()` — adding a position never touches the websocket subscription list, see below
- `PATCH /api/positions/{id}` — update shares/avg_cost/notes
- `DELETE /api/positions/{id}` — remove (e.g. fully sold). No `FinnhubClient.unsubscribe()` call — there's nothing to unsubscribe, since `Position` never subscribes in the first place
- `GET /api/portfolio/summary` — aggregate `total_invested`, `total_market_value`, `total_unrealized_gain`, `total_unrealized_gain_pct` across all positions, same per-ticker price-source split as above

**Live price source (revised 2026-08-10 — supersedes the 2026-08-02 decision to auto-subscribe every `Position`; corrected 2026-08-12 — see below):** `FinnhubClient`'s websocket subscription list stays **exclusively `StockAlert`-driven** — a `Position` never calls `subscribe()`/`unsubscribe()` on its own, regardless of how many positions exist. `GET /api/positions`/`GET /api/portfolio/summary` read `StockAlert.last_price` for a ticker with an active alert, and fall back to a per-ticker REST `get_price()` call for any position with no alert on it.

**Correction (2026-08-12) — no live in-memory price cache actually exists.** Earlier revisions of this note (and `.doc/architecture.md`'s callout) described alert-backed tickers as reading from "`FinnhubClient`'s in-memory websocket-fed cache." Checked against the actual code (`stocks.py`): `_AlertState` (the only thing `FinnhubClient._cache` stores) has no price field at all, and `StockAlert.last_price` is written in exactly one place — inside `_fire_event`, which only runs at the instant a threshold *crosses* (`_check_threshold:192`). A tick that moves the price without crossing never touches it; recovery (`_clear_alerted_at`) doesn't touch it either. So `last_price` is **not** a live/current price — it's "the price the last time this alert fired," `null` if it's never fired, and stale indefinitely between crossings despite Finnhub actively streaming ticks for that ticker the whole time. `GET /api/positions`' enrichment for an alert-backed ticker inherits this same staleness — it is correctly described as "avoids a redundant REST call," not as "gets a fresh live price." Building an actual live per-tick cache (closer to the original 2026-08-02 design's `{ticker: {price, updated_at}}` proposal) is a real, separate piece of work against already-shipped `#4` code, not something this issue does.

Rationale: the websocket is one connection shared across the whole app, capped at ~50 symbols (corroborated across multiple sources, not confirmed against Finnhub's own primary docs) — not scoped per-holding. A portfolio of normal size (20-30+ positions is unremarkable) risked exhausting that budget on its own under the original design, and unlike an alert (explicit, user-managed, naturally stays small) a holding is rarely removed once bought — the subscribed count would only ratchet upward over time with no natural release valve. A held-but-un-alerted position only needs *display-fresh* pricing (matters while a page is open); it doesn't need *alert-grade* pricing (must fire even when nobody's looking) — REST `get_price()` + the frontend's existing SWR poll already covers that without spending a scarce, effectively-permanent resource on it. Full reasoning: `.doc/architecture.md` → "Finnhub WebSocket Flow" callout.

Frontend still does plain REST + SWR polling against `GET /api/positions` — same convention as `#10.1`/`#10.4`/`#30`, unaffected by this revision either way (a websocket/SSE channel to the browser was never proposed for Positions, before or after).

**Backend caching (added 2026-08-12):** `get_price()` (`stocks.py:237`) gets a short in-memory TTL cache (`{ticker: (price, fetched_at)}`, ~10-15s), added once — not per-caller. Doesn't reduce staleness (the poll interval already governs that); it collapses redundant Finnhub REST calls when the same un-alerted ticker gets requested from more than one place at nearly the same moment — e.g. two browser tabs polling `GET /api/positions` at slightly different alignment, or a ticker that's both an un-alerted `Position` here and independently shown on `#31`'s `/market/{ticker}/details` page in another tab. `#30`'s `GET /api/market/trending` already does an equivalent server-side shared cache (`issues.md`'s `#30` section) — this extends the same principle to `get_price()`, the other REST call path.

Shared-subscription accounting between `Position` and `StockAlert` (refcounting, etc.) is no longer applicable — `Position` never subscribes, so there's nothing to refcount. Simpler than the original design specifically because of this revision.

**Logo (decided 2026-08-02):** rendered directly in the frontend as `<img src="https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/{ticker}.png">` — no backend call at all. Live-tested as an unauthenticated static asset (no API key needed): `200`/real PNG for real stock tickers (including ones with punctuation, e.g. `BRK.B`), `404`/JSON error body for ETFs and invalid tickers. `onError` on the `<img>` falls back to the existing colored-placeholder box. No caching needed beyond normal browser/CDN HTTP caching — this isn't an authenticated or rate-limited call, so there's nothing to protect it from.

**`/portfolio` page (dashboard):**
- Holdings table: real ticker logo (or placeholder fallback), ticker, shares, avg cost, current price, market value, unrealized gain ($ and %), color-coded
- Summary card: total portfolio value, total invested, total gain/loss
- Add/edit/delete position form

### Why (context)

User wants portfolio insights in-app while continuing to trade directly on Wealthsimple. Wealthsimple has no official API. Investigated two alternatives:
- Unofficial reverse-engineered libraries (`wsimple`, `ws-api-python`, etc.) — real account-lockout risk (ToS bans automated scraping; trading-via-API is actively detected and enforced, read-only access is an unenforced gray area but still technically covered by the ToS's scraping clause), and they require holding real Wealthsimple credentials/session tokens directly in this app's infra.
- SnapTrade — a legitimate paid third-party aggregator with OAuth-style, default-read-only Wealthsimple integration. Avoids the credential-custody problem, but adds cost (pricing not confirmed) and a new third-party trust dependency.

Decided: manual entry for now. No new external dependency, no credential-security surface, consistent with how the rest of this app already works (user tells it what to track — nothing auto-discovered). SnapTrade sync remains an option later if manual upkeep becomes annoying enough to be worth paying for.

### Acceptance criteria

- [ ] `POST /api/positions` creates a position, validates ticker via Finnhub REST — does **not** subscribe it on `FinnhubClient`
- [ ] Adding/removing/updating a `Position` never calls `FinnhubClient.subscribe()`/`unsubscribe()` — the websocket subscription list is affected only by `StockAlert` CRUD (`#4`), unchanged by this issue
- [ ] `GET /api/positions` reads `current_price` from `StockAlert.last_price` for a ticker with an active alert (accepting that field's known staleness — see "Correction," above), and from a REST `get_price()` call for a position with no alert
- [ ] `get_price()` results are cached in-memory for ~10-15s — confirmed via two near-simultaneous requests for the same un-alerted ticker producing only one Finnhub REST call
- [ ] `PATCH /api/positions/{id}` updates shares/avg_cost/notes
- [ ] `GET /api/portfolio/summary` returns correct aggregate totals using the same per-ticker price-source split (cache for alerted tickers, REST for the rest)
- [ ] `/portfolio` page displays holdings table (with real per-ticker logos, placeholder fallback on load error) + summary card
- [ ] Manual add/edit/delete flow works end-to-end in the UI

---

## Group 6 — iOS

---

## [❌ Removed] Issue #12 — iOS SwiftUI Token Registration App

**Removed:** Replaced by Pushover. No Apple Developer account or APNs infrastructure needed — Pushover covers iPhone, iPad, Mac, and Apple Watch via a single HTTP POST to `api.pushover.net`.

---

## Group 7 — Deployment

---

## [ ] Issue #13 — Pi Deployment + Tailscale

**Type:** ops / HITL
**Estimate:** ~3h
**Blocked by:** #8, #10.1–#10.5
**HITL reason:** Requires physical Raspberry Pi, Tailscale account, and manual SSH access for initial setup.

### Local dev note (2026-07-22)

**Until the Pi exists, run the backend locally via its own venv (`backend/.venv/bin/uvicorn app.main:app --reload`) instead of through `docker compose` — don't fight Docker Desktop for this.** Root cause: Docker Desktop on Mac runs containers inside a hidden Linux VM with its own private network; that VM has no route to the real home LAN (where the Synology NAS's Postgres lives at `<nas-ip>`), even though the Mac itself reaches it fine natively. Tried and ruled out: `NetworkType: vpnkit` override (ignored by this Docker Desktop version), switching VMM from Apple Virtualization Framework to Docker VMM, macOS's Local Network permission toggle (helped partially — changed the failure from instant refusal to timeout, didn't fully fix it). A `socat`/`ssh -L` port-forward through `host.docker.internal` would work but adds a background process to babysit for zero benefit over just running the backend directly, since the Mac already has native LAN access. This entire class of problem doesn't exist on the Pi — it runs Linux directly, no hidden VM, so a container there has the same LAN access as any other Pi process. Revisit Docker-for-local-dev only if a real need arises before `#13` lands.

### Pi provisioning note (2026-08-09)

**Hardware exists now — a Pi 4B 8GB, not a Pi 5 (corrected in `[[project-hardware]]`).** Base OS provisioning done ahead of this issue's formal start (still correctly blocked by `#10.1`–`#10.5`, not yet complete):

- Raspberry Pi OS Lite (64-bit) etched via Raspberry Pi Imager, headless (SSH + user preset via Imager's advanced options — gear icon must be set *before* writing, easy to forget on a re-etch)
- SSH reachable both on LAN (`youn-server.local` / `<pi-lan-ip>`) and via Tailscale (`<pi-tailscale-ip>`) — Tailscale installed and joined on both Pi and dev Mac
- Docker Engine installed (`get.docker.com` script), `youn` user in `docker` group (no `sudo docker` needed)
- Node.js 24 (NodeSource LTS repo) + Claude Code CLI installed and authenticated — lets Claude Code run directly on the Pi over SSH, independent of this deployment issue
- Login: see `[[project-pi-credentials]]` memory (not committed to repo)

**Not done yet** (remains this issue's actual scope): cloning this repo onto the Pi, `.env` population, `docker compose up -d`, TradingAgents venv-in-container setup, systemd/restart policy, end-to-end Pushover test. Deliberately deferred — still iterating on app issues locally first.

### What to build

Deploy the full stack to Raspberry Pi and verify end-to-end alert flow over Tailscale.

- Install Tailscale on Pi: `curl -fsSL https://tailscale.com/install.sh | sh && tailscale up`
- Install Tailscale on iPhone, iPad, Mac — all joined to same Tailscale account
- Install Pushover app on each Apple device (iOS: $4.99 one-time, macOS: $4.99 one-time)
- Copy `.env` to Pi; `chmod 600 .env`
- Populate `.env` with `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `API_KEY`, `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY`, `TRADINGAGENTS_LLM_PROVIDER=anthropic`, `TRADINGAGENTS_OUTPUT_LANGUAGE=English`
- No volume mounts needed for DB — PostgreSQL runs on Synology NAS (native DSM package, persistent storage on RAID)
- **TradingAgents host setup** (validated on Mac during dev — identical steps on Pi, only the machine changes):
  ```bash
  sudo mkdir -p /opt/tradingagents
  sudo chown $(whoami) /opt/tradingagents
  git clone https://github.com/TauricResearch/TradingAgents /opt/tradingagents
  ```
  `docker-compose.yml` backend service already mounts `/opt/tradingagents:/opt/tradingagents` (volume, not baked into the image — see `.doc/architecture.md`'s "TradingAgents Update & Run Flow" for why: this is what lets the update endpoint apply without a redeploy).
- `docker compose up -d` on Pi; verify both containers running
- Build TradingAgents' venv **inside the running container** (not on the Pi host directly — keeps it isolated from the backend's own Python deps, and guarantees matching architecture/glibc without needing to think about it):
  ```bash
  docker compose exec backend python -m venv /opt/tradingagents/.venv
  docker compose exec backend /opt/tradingagents/.venv/bin/pip install -r /opt/tradingagents/requirements.txt
  docker compose exec backend /opt/tradingagents/.venv/bin/python -c "import tradingagents"
  ```
  (Last command is a smoke test — confirms the venv actually works before relying on it. On Mac this needed a Docker Desktop → Settings → Resources → File Sharing entry for `/opt`; the Pi's plain Docker Engine has no such restriction, so that step is Mac-only and shouldn't be needed here.)
- **Optional shortcut — reuse existing local clone instead of a fresh `git clone`:** a working TradingAgents checkout already exists at `/Users/youn/Documents/tools/TradingAgents` on the dev Mac (tracks `TauricResearch/TradingAgents` upstream, has a validated `ANTHROPIC_API_KEY` in its own `.env`). Copying that folder to the Pi (rather than cloning fresh) skips the clone step and carries over a known-working API key. Two things to know if doing this:
  - Its existing `.venv` **cannot** be reused — built on macOS (Darwin binaries), won't run in the Pi's Linux container. Still build a fresh one via the `docker compose exec` commands above.
  - TradingAgents auto-loads `.env` from its own directory via `python-dotenv`'s `load_dotenv(find_dotenv(usecwd=True))` with `override=False` — so its `.env` fills in `ANTHROPIC_API_KEY` etc. as a fallback only where this project's own root `.env` doesn't already set them. Set `ANTHROPIC_API_KEY` explicitly in this project's `.env` regardless, for clarity — don't rely on the fallback silently.
  - On the dev Mac specifically, this was done as a **symlink** rather than a copy — `sudo ln -s /Users/youn/Documents/tools/TradingAgents /opt/tradingagents` — so `/opt/tradingagents` resolves without duplicating the clone. Required the Docker Desktop File Sharing step above (add `/opt`) before the bind mount would be permitted.
  - **Cleanup once the Pi is deployed:** remove the dev Mac's `/opt/tradingagents` symlink (`sudo rm /opt/tradingagents`) — it's local dev-only scaffolding, not needed once the Pi is the primary running environment. Safe to leave in place if still doing backend dev locally afterward; just don't forget it's there.
- Systemd service (or `--restart unless-stopped`) for auto-start on Pi reboot
- End-to-end test: add a stock alert, trigger `POST /api/poll/stocks`, confirm Pushover push received on all devices

### Acceptance criteria

- [ ] Pi and all Apple devices appear in Tailscale dashboard with stable IPs
- [ ] `docker compose up -d` starts both containers on Pi without error
- [ ] Containers restart automatically after `sudo reboot`
- [ ] `.env` has `chmod 600`
- [ ] `GET /api/health` reachable from iPhone over Tailscale (Tailscale IP)
- [ ] Pushover push notification received on iPhone, iPad, Mac, and Apple Watch
- [ ] Email alert received at configured Gmail address
- [ ] PostgreSQL on NAS reachable from Pi after `docker compose restart` (verify via `GET /api/health`)
- [ ] `docker compose exec backend /opt/tradingagents/.venv/bin/python -c "import tradingagents"` succeeds
- [ ] `POST /api/stockalerts/{id}/analyze` on a real alert completes end-to-end (`status`: `pending → running → done`), confirming the venv-in-container + volume mount actually work on the Pi, not just on Mac dev

---

## [ ] Issue #13.1 — Tailscale Subnet Routing (NAS Postgres Reachability)

**Type:** ops / HITL
**Estimate:** ~0.75h
**Blocked by:** None — Tailscale already installed/joined on Pi and dev Mac per `#13`'s provisioning note
**HITL reason:** Requires Pi SSH access, Synology DSM access, and a one-time click in the Tailscale admin console.

### What to build

Off the home LAN, `DATABASE_URL` (`<nas-ip>:5433`, the NAS) isn't
reachable even with Tailscale joined, since Tailscale only makes the Pi
itself reachable — not other devices on the Pi's LAN. Configure the Pi as a
Tailscale subnet router advertising just the NAS host (`<nas-ip>/32`, not
the full `/24` — least-privilege: a compromised tailnet device should only
gain a path to the Postgres port, not the whole home LAN), and tighten the
NAS's `pg_hba.conf` from `0.0.0.0/0` to `<lan-subnet>/24` (closing the TODO left
open since `#1.5`), relying on Tailscale's default SNAT behavior so
Postgres sees the connection as coming from the Pi's LAN IP.

See `.plan/13.1-tailscale-subnet-routing/` for the full step-by-step runbook
(IP forwarding persistence, route advertisement + admin console approval,
Mac-side accept-routes check, `pg_hba.conf` edit, and on-LAN regression
testing).

### Acceptance criteria

- [ ] Pi advertises route `<nas-ip>/32` via Tailscale, persisted across reboots (`tailscale set --advertise-routes=...`, not just `up`)
- [ ] Route approved in Tailscale admin console
- [ ] `net.ipv4.ip_forward=1` set persistently on the Pi (`/etc/sysctl.d/`, survives `sudo reboot`)
- [ ] Dev Mac has "Accept subnet routes" enabled and can reach `<nas-ip>:5433` while off the home LAN
- [ ] `backend/.venv/bin/uvicorn app.main:app --reload` starts cleanly off-LAN with `DATABASE_URL` unchanged
- [ ] NAS `pg_hba.conf` tightened to `<lan-subnet>/24` for the `youn_server` database; PostgreSQL package restarted
- [ ] Existing on-LAN Postgres access (from the Pi, from a Mac on the LAN) still works after the `pg_hba.conf` change
- [ ] Route and IP forwarding both survive a `sudo reboot` of the Pi

---

## Group 8 — Testing

---

## [ ] Issue #14 — Integration Tests

**Type:** test / AFK
**Estimate:** ~4h
**Blocked by:** #3, #4, #5, #7, #8

### What to build

Test suite covering all deep modules through their public interfaces. No mocking of the module under test — only external dependencies (network, subprocess, filesystem).

**Scraper tests (`tests/test_scraper.py`):**
- `RetailerRouter`: assert `amazon.ca` → `AmazonCAScraper`; unknown domain → `HTTPScraper`
- `HTTPScraper` schema.org: mock httpx with JSON-LD fixture; assert `ScraperResult(price=float, status="ok")`
- `HTTPScraper` Shopify: mock `/products/{handle}.json`; assert price from `?variant=` param if present, else `variants[0]`
- `HTTPScraper` OOS: mock Shopify JSON with `available: false`; assert `ScraperResult(price=None, status="oos")`
- `HTTPScraper` error: mock connection error; assert `ScraperResult(price=None, status="error")` without raise
- `_parse_price`: table-driven tests covering `"$1,299.99"`, `"1 299,99"`, `"CAD 129.99"`, `"129.00"`

**Stock service tests (`tests/test_stocks.py`):**
- Mock Finnhub WebSocket tick; assert threshold crossing produces correct `STOCK_THRESHOLD` event
- Mock Finnhub WebSocket tick below threshold; assert no event produced
- Mock Finnhub REST `/api/v1/quote`; assert `validate_ticker("AAPL")` returns `True`; `validate_ticker("INVALID_XYZ")` returns `False`
- Simulate Finnhub REST failure; assert `get_price()` returns `None` without raise
- Mock yfinance `Ticker.history()`; assert `get_price_history()` returns correct list of price points

**Notification tests (`tests/test_notify.py`):**
- Mock httpx; assert Pushover POST has correct payload shape (`token`, `user`, `title`, `message`)
- Simulate Pushover HTTP 4xx → assert error logged, email still attempted
- Assert email failure does not prevent Pushover call (and vice versa)

**Consumer tests (`tests/test_consumers.py`):**
- Write `PRICE_DROP` event; run dispatcher; assert event marked `processed` and `send_alert` called
- Write event with `run_analysis = False`; run `AnalysisConsumer`; assert no `AnalysisResult` row created
- Write two identical pending events; run consumer; assert second is not double-processed

**Alert deduplication tests (`tests/test_dedup.py`):**
- `alerted_at` set → assert second poll cycle does not write a second `Event` row
- Price recovers above target → assert `alerted_at` cleared
- Price drops again after recovery → assert new `Event` row written

**API route tests (`tests/test_api.py`):**
- FastAPI test client with test DB (SQLite in-memory or dedicated test Postgres)
- Assert 401 on missing `X-API-Key` for all protected routes
- Assert 200 on `GET /api/health` with no auth
- Assert `POST /api/stockalerts` with invalid ticker returns 400
- Assert `POST /api/stockalerts` with duplicate ticker returns 409 or upserts cleanly

### Acceptance criteria

- [ ] `pytest backend/` passes with 0 failures
- [ ] Scraper router tests cover: amazon.ca, bestbuy.ca, walmart.ca, unknown domain
- [ ] Stock service tests cover: WebSocket tick → event, Finnhub REST validate, yfinance history, REST failure → None
- [ ] Pushover HTTP 4xx test confirms error logged and email still attempted
- [ ] Consumer deduplication test confirms no double-processing
- [ ] Alert re-arm test confirms `alerted_at` cleared and new event fires on second drop
- [ ] All API auth tests pass (401 on missing key, 200 on health)

---

## [ ] Issue #29 — Frontend Test Suite (Vitest Setup + Watchlist Components + Proxy Route)

**Type:** test / AFK
**Estimate:** ~3h
**Blocked by:** None

### What to build

No test framework exists in `frontend/` yet (`frontend/package.json` has zero test dependencies) — this issue sets one up and closes the two concrete gaps identified so far.

**Setup:**
- Add **Vitest** (fast, native ESM/TS support, no browser environment needed to unit-test a plain async function like a Next.js route handler)
- Wire a `test` script into `frontend/package.json`

**Proxy route tests (`app/api/proxy/[...path]/route.ts`)** — scenarios already scoped in `.doc/test.md`:
- Request to `/api/proxy/system/storage` forwards to `${BACKEND_URL}/api/system/storage` (segments correctly rejoined)
- `X-API-Key` header is attached server-side from `process.env.API_KEY` — never present on the *incoming* browser request
- Backend `200` response relayed unchanged (status + body)
- Backend `503` response relayed unchanged, not swallowed/converted
- Query params (`request.nextUrl.search`) forwarded onto the backend URL

**Watchlist page tests (`app/watchlist/page.tsx`)** — the highest-value target is `sheetEditReducer`, a pure function with no rendering/DOM involved:
- Every action (`editName`, `editTargetPrice`, `editListing`, `addListing`, `setDraft`, `cancel`) produces the correct next state from `{ type: "none" }` and from each other edit mode
- Starting a new edit mode while another is already active fully replaces state (proves the mutual-exclusivity guarantee the reducer was specifically designed for)
- `setDraft` on `{ type: "none" }` is a no-op (returns state unchanged)
- `isValidUrl`: accepts `http:`/`https:` URLs, rejects malformed strings, rejects `javascript:`/`data:` schemes
- Component-level: typing an invalid URL into the Add Item textarea keeps Save disabled; fixing it enables Save; the last remaining listing's Remove button is disabled

### Why (context)

Surfaced during a `/code-reviewer` pass over the Synology fix + `/watchlist` page (2026-07-28) — flagged as Major (zero frontend test coverage for ~600 lines of new interactive UI) and deferred at the time ("to be done later") rather than blocking that work. `sheetEditReducer` in particular is exactly the kind of pure, exhaustively-testable function that's cheap to lock down and easy to accidentally regress later (e.g. a new edit mode added without updating every case). The proxy route tests were already planned in `.doc/test.md` before this review; bundled here since both need the same Vitest setup step and neither is useful in isolation.

Not blocked on `#24`/`#10.1`–`#10.5`: `/watchlist` already exists in the repo as a mock-data prototype (shipped ahead of its own backend, same pattern as `#22`'s bentobox dashboard), and the reducer/validator logic under test doesn't depend on a real backend existing — only on the component code, which is already written.

**Forward-looking note (surfaced while grilling `#36`, not scoped into this issue):** once `#36` lands, the watchlist page gains `EventSource`-based live updates — testing that will need mocking a streaming connection (no native `EventSource` in the Vitest/jsdom environment by default), a real but well-trodden concern, not a design fork. Not part of this issue's scope since `#36` doesn't exist yet at time of writing; whichever issue adds SSE test coverage should account for it separately.

### Acceptance criteria

- [ ] `npx vitest run` passes with 0 failures from `frontend/`
- [ ] Proxy route: all 5 scenarios above covered
- [ ] `sheetEditReducer`: every action type covered, including the mutual-exclusivity and no-op cases
- [ ] `isValidUrl`: valid http(s), malformed string, and unsafe-scheme cases all covered
- [ ] At least one component-level test confirms the Add Item Save button's disabled state reacts to URL validity

---

## [ ] Issue #15 — Headless Chromium Bot Detection on Pi

**Type:** ops / AFK
**Estimate:** ~2h
**Blocked by:** #3, #13

### Background

During local smoke testing (Issue #3), BestBuy and SSENSE returned 403 in headless Patchright but passed immediately with `headless=False`. Amazon served a stripped decoy page headless but loaded correctly headful after a homepage warm-up navigation. This confirms the blocker is headless detection (Chromium DevTools fingerprint), not IP reputation or request rate.

The production environment is a Raspberry Pi 5 running Docker (`mcr.microsoft.com/playwright/python:v1.52.0-jammy`). The Pi has no physical display, so `headless=False` is not directly usable in production without a virtual framebuffer.

### What to validate first

Patchright applies CDP-level patches specifically to defeat headless Chromium fingerprinting. The `mcr.microsoft.com/playwright/python` Docker image uses a separate Chromium build that Patchright targets. It's plausible that headless works fine on Pi/Docker even though it failed locally — local Chromium and Docker-bundled Chromium differ.

**Step 1 — run `smoke_test.py --patchright` inside the Docker container on Pi after #13 deployment.** If BestBuy and SSENSE return `status="ok"`, no further action needed; headless is working.

### Fallback: Xvfb virtual framebuffer

If headless detection persists on Pi, add a virtual display to the Docker container:

```dockerfile
# In backend/Dockerfile — before the CMD line
RUN apt-get install -y xvfb
```

```python
# In patchright_scraper.py start_browser()
import subprocess, os
_xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1920x1080x24"])
os.environ["DISPLAY"] = ":99"
# then launch_persistent_context(..., headless=False)
```

This makes the container launch a headless X11 server internally and run Chromium in "headed" mode against it. Chromium sees a real display; bot detectors see a headed browser. Resource cost is minimal (~30 MB RAM).

### Known limitations

- **BestBuy** may remain blocked even with Xvfb. BestBuy uses a Cloudflare WAF with TLS/JA4 fingerprinting — even a headed Chromium can be fingerprinted by its TLS handshake before any HTML is served. If BestBuy blocks on Pi regardless of headless/headed, treat it as unsupported and remove from `RETAILER_MAP` or mark as `scraper_type=null`.
- **Amazon** works headful with the `[data-pricetopay-label]` semantic selector + `.a-offscreen` regex fallback. These selectors are stable because Amazon's own JS depends on them internally. If headless also works on Pi Docker (Step 1), Amazon needs no Xvfb.

### Acceptance criteria

- [ ] Smoke test `--patchright` passes on Pi Docker for: `deadstock.ca` (Shopify), `ssense.com` (Next.js), `amazon.ca`
- [ ] If Xvfb path taken: Dockerfile builds cleanly on ARM64 with `xvfb` installed
- [ ] If Xvfb path taken: `start_browser()` starts Xvfb subprocess before Chromium launch, cleans up on `close_browser()`
- [ ] BestBuy result documented: `ok`, `oos`, or marked unsupported with rationale

---

## [ ] Issue #16 — Tailscale MagicDNS (Human-Readable Hostnames)

**Type:** ops / HITL
**Estimate:** ~0.5h
**Blocked by:** #13
**HITL reason:** Requires Tailscale admin console access — no code change.

### What to build

Replace raw Tailscale IPs with human-readable names for the Pi and NAS, so devices are reached as `http://pi:8000/` instead of `http://100.x.y.z:8000/` when off-LAN. Chosen over a purchased domain or mDNS `.local` names — `.local` doesn't resolve off-LAN, and a domain is unneeded complexity/cost given remote access already goes through Tailscale (see `.doc/architecture.md` / project network notes).

- Tailscale admin console → **DNS** tab → enable **MagicDNS**
- Rename Pi and NAS to clear names in the admin console (Settings → machine name) if the auto-assigned names aren't already readable
- Update any bookmarks or docs that reference raw Tailscale IPs to use the new MagicDNS names
- **Do not** change `backend/.env`'s `DATABASE_URL` to a Tailscale/MagicDNS name — Pi→NAS Postgres traffic should stay on the local LAN (`<nas-ip>`), not get routed through the Tailscale overlay network

### Acceptance criteria

- [ ] MagicDNS enabled in Tailscale admin console
- [ ] Pi and NAS have human-readable names (not auto-generated gibberish) in the Tailscale admin console
- [ ] `http://<pi-name>:8000/api/health` resolves and responds from an off-LAN device on the tailnet
- [ ] `backend/.env`'s `DATABASE_URL` unchanged — still points at the NAS LAN IP, not a Tailscale name
- [ ] Any bookmarks/docs referencing raw Tailscale IPs updated to the new MagicDNS names

---

## [ ] Issue #20 — youn-server Self-Update (Version Check + Auto-Apply)

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #8, #13

### What to build

Same "update available" pattern as TradingAgents' version check/update, applied to youn-server's own codebase — with one structural difference driven by how the backend is actually deployed (see Why below).

**Build-time commit tagging:**
- `backend/Dockerfile`: `ARG GIT_COMMIT=unknown` + `ENV GIT_COMMIT=${GIT_COMMIT}`
- Build invocation passes `--build-arg GIT_COMMIT=$(git rev-parse HEAD)`
- `app/core/config.py`: new `git_commit: str = "unknown"` setting reads it

**`GET /api/system/version`:**
- Compares baked-in `settings.git_commit` against GitHub's REST API for the latest commit on `main` (`GET https://api.github.com/repos/<owner>/youn-server/commits/main`)
- Repo is **private** — needs `GITHUB_TOKEN` (PAT, `repo` read scope) as `Authorization: Bearer <token>`, unlike TradingAgents' public-repo check which needed no auth
- Returns `{ current_commit, latest_commit, update_available, behind_count }` — same shape as `GET /api/analysis/tradingagents/version` for UI consistency (optionally via GitHub's compare API for `behind_count`)

**`POST /api/system/update`:**
- Triggers, via Docker socket access, the full cycle: `git pull` (host, private repo — same `GITHUB_TOKEN` or a deploy key for git auth over HTTPS), `docker compose build backend`, `docker compose up -d backend`
- Implementation: Docker SDK for Python (`docker` package) talking to the mounted socket, not shelling out to a `docker` CLI binary — avoids needing the CLI installed inside the backend image
- Since this restarts the container the request is running in, response sequencing needs care — client must get `{ success, new_commit, output }` back before (or despite) the container going down
- Old container should stay up if the build fails, so a bad update doesn't take the server down — this is the one real safety property worth getting right

**`docker-compose.yml`:**
- Mount `/var/run/docker.sock:/var/run/docker.sock` into the backend service, with an explicit comment on what this grants (see Why)

**`.env`:** add `GITHUB_TOKEN`

### Why (context)

TradingAgents' code is live-mounted (a Docker volume, not baked into the image), so its update is just a `git pull` — no rebuild, no downtime, because nothing about the backend container's own filesystem changes. youn-server's own backend is the opposite: `build: ./backend` bakes the code into the image at build time. There's no live git clone inside the running container to `git pull` against — applying an update genuinely means rebuilding the image and replacing the container, the same "copy" tradeoff discussed (and rejected) as a hypothetical alternative for TradingAgents, except here it's simply how the backend already works, not a choice being reconsidered.

Chose to trigger this from the app itself (Docker-socket-mounted) rather than requiring manual SSH + three commands, per user preference. This is a real, deliberate privilege escalation: mounting `/var/run/docker.sock` gives the backend container effective control over the entire host's Docker daemon — every other container, every volume — not just permission to restart itself. Scoped specifically for this one feature; the docker-compose.yml comment should say so explicitly, and this shouldn't become a pattern reached for casually elsewhere.

TradingAgents' repo is public, needing no auth for its version-check. youn-server's repo is private, so this needs `GITHUB_TOKEN` for both the read-only version check and `git pull` authentication — a new secret this project doesn't currently have.

### Acceptance criteria

- [ ] `GET /api/system/version` returns correct `current_commit`/`latest_commit`/`update_available` against the private repo using `GITHUB_TOKEN`
- [ ] `POST /api/system/update` runs `git pull` + `docker compose build backend` + `docker compose up -d backend` via the Docker socket
- [ ] Client receives a response despite the backend container restarting mid-operation
- [ ] `docker-compose.yml`'s docker-socket mount has an explicit comment documenting the privilege implication
- [ ] Build failure leaves the old container running — a bad update doesn't take the server down
- [ ] Dashboard shows "update available" + trigger button, matching #11's TradingAgents version panel pattern

### Open question (2026-07-23)

- Frontend should show a confirmation dialog before triggering `POST /api/system/update` — user needs to know the server will restart/be briefly unreachable before committing.
- `SystemRestartTile` (`frontend/src/components/tiles/system-restart-tile.tsx`) is currently unwired — no backend endpoint exists for it anywhere in this repo. Its restart action likely wants to share this issue's Docker-socket restart capability rather than introduce a second one. Needs its own decision: does "System Restart" mean `docker compose restart` (containers only) or a full Pi reboot? Different scope, not yet decided.

---

## [ ] Issue #21 — System/Infra Status API (Docker, Pi Resources, Services, Schedules)

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #8, #20

### What to build

Read-only backend endpoints exposing host-level and app-internal process status for the overview dashboard (#22) — container health, Pi hardware metrics, plus this app's own long-running processes and scheduled jobs. Deliberately excludes repo-update-check logic — #11 and #20 already built that (`GET /api/analysis/tradingagents/version`, `GET /api/system/version`), #22 calls those two directly for its update-notification tile.

**Host-level:**
- **`GET /api/system/docker`** — list running containers via the Docker socket: name, status (`running`/`exited`/`restarting`), image, uptime. Reuses the `docker.sock` mount and `docker` Python SDK dependency #20 already introduces — no new mount, no new privilege decision to make here.
- **`GET /api/system/resources`** — host resource snapshot via `psutil`: CPU %, memory %, disk %. Plus Pi temperature, read from `/sys/class/thermal/thermal_zone0/temp` (Pi-specific, not part of `psutil`) — degrades to `null`/omitted rather than erroring if that path doesn't exist (e.g. local dev on a non-Pi host).

**App-internal:**
- **`GET /api/system/services`** — health of this app's own long-running processes, reading state already sitting on `app.state` from `main.py`'s lifespan (no new instrumentation needed): Finnhub WebSocket `connected` status, event-dispatcher task alive/crashed (`dispatch_task.done()` / `.exception()`), event-queue backlog size (`event_queue.qsize()`).
- **`GET /api/system/schedules`** — per-job status for APScheduler jobs. `next_run_time` is free (APScheduler tracks it natively via `scheduler.get_jobs()`). Last-run outcome + timestamp per job is **not** free — needs a new `scheduler.add_listener(callback, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)` recording the last outcome into a small in-memory dict, since APScheduler doesn't retain job history itself. Covers the existing 6h price-poll job today; extensible for the pending NAS-poll job once it exists.

### Why (context)

The overview dashboard (#22) needs infra-tile data; nothing today exposes Docker container state, Pi hardware metrics, or this app's own internal process/job health via API. Host-level endpoints sequenced after #20 specifically to piggyback on the `docker.sock` mount and its documented privilege tradeoff already accepted there, rather than introducing a second socket-mount decision for the same container. App-internal endpoints exist because failure here is currently silent — e.g. if the Finnhub WebSocket drops or the event dispatcher task ever exits, nothing surfaces that short of reading server logs.

### Acceptance criteria

- [ ] `GET /api/system/docker` returns running containers' name/status/image/uptime
- [ ] `GET /api/system/resources` returns CPU/mem/disk % and Pi temperature
- [ ] Both Docker/resource endpoints reuse #20's existing `docker.sock` mount/SDK dependency — no new privilege surface introduced
- [ ] Pi-temperature read degrades gracefully (omitted, not an error) when `/sys/class/thermal/thermal_zone0/temp` doesn't exist
- [ ] `GET /api/system/services` returns Finnhub WS connected status, dispatcher-task alive/crashed state, event-queue backlog size
- [ ] `GET /api/system/schedules` returns next-run-time and last-run outcome/timestamp per registered job

---

## [✅] Issue #21.5 — Synology Storage Status API

**Type:** feat / AFK
**Estimate:** ~1h
**Blocked by:** #1.5

### What to build

Read-only backend endpoint exposing Synology NAS storage/bay health — independent of #21's Docker/Pi-resources scope (no Docker socket, no #20 dependency); shipped ahead of schedule alongside the first dashboard UI pass.

- `app/services/synology.py`: `SynologyClient` — logs into DSM (`SYNO.API.Auth`), queries `SYNO.Storage.CGI.Storage`, parses per-bay disk status (`healthy`/`warning`/`error`/`empty`) and volume/pool sizes into available/used/reserved TB; logs out when done
- `app/schemas/system.py`: `BayResponse`, `StorageResponse` Pydantic schemas
- `app/api/system.py`: `GET /api/system/storage` — returns bays + available/used/reserved; 503 if Synology client disabled or unreachable
- `core/config.py`: `synology_host`/`port`/`user`/`password`/`use_https`/`verify_ssl` settings — disabled gracefully (logged warning, `None` return) when host/user/password unset
- `smoke_test.py --synology`: manual smoke test against a real NAS

### Acceptance criteria

- [x] `GET /api/system/storage` returns bay statuses + available/used/reserved TB from a real Synology NAS
- [x] Missing Synology credentials → client disabled, endpoint returns 503, no crash
- [x] Login/logout session handled per-request (no leaked DSM sessions)
- [x] Frontend `StorageTile` consumes this endpoint live via `/api/proxy/system/storage`

---

## [ ] Issue #22 — Overview Dashboard (`/`, Bentobox Summary)

**Type:** feat / AFK
**Estimate:** ~4h
**Blocked by:** #10.1–#10.5, #11, #19, #20, #21

### What to build

Replaces the plain `/` → `/wishlist` redirect originally planned under #10 with a bentobox-style summary page — minimum-viable, at-a-glance status across both app data and host infra. No new backend logic of its own; every tile calls an endpoint another issue already built.

**`/` page — bentobox tile grid:**
- **Wishlist tile** — name-only list (or count) of active `WatchItem`s, from #10.1's `GET /api/items`
- **Portfolio summary tile** — ticker + shares per position, from #19's `GET /api/positions` (current price/market value already live-enriched server-side — no new polling code needed)
- **Docker health tile** — from #21's `GET /api/system/docker`
- **Pi resources tile** — from #21's `GET /api/system/resources`
- **Services tile** — Finnhub WS connection, dispatcher task health, event-queue backlog, from #21's `GET /api/system/services`
- **Schedules tile** — next-run-time + last-run outcome per job, from #21's `GET /api/system/schedules`
- **Update notification tile** — TradingAgents and youn-server update status together, one tile, from #11's `GET /api/analysis/tradingagents/version` and #20's `GET /api/system/version`
- SWR polling, matching #10.1's established 30-second refresh interval

### Why (context)

Consolidates a single-glance summary the user asked for, spanning both this app's own data (wishlist, holdings) and the underlying Pi's infra state (Docker, resources, pending updates on both TradingAgents and youn-server itself). Kept as its own issue rather than folded into #10.1–#10.5 because it depends on #19, #20, and #21 — none of which exist when #10.1–#10.5 ships; #10.1–#10.5 ships first with the plain redirect, this issue swaps it for the real dashboard once all five data sources exist.

### Progress note (2026-07-21)

A first static-markup pass of this bentobox shell shipped ahead of its listed blockers — `frontend/src/app/page.tsx` renders the tile grid (date, cpu, memory, storage, docker×2, git-update×2, uptime, system-restart, services, portfolio, watchlist) using shadcn/ui primitives. Only the storage tile is wired to a real endpoint (#21.5's `GET /api/system/storage`, via the Next.js proxy); Docker, Git-update, Uptime, Portfolio, and Watchlist tiles still render hardcoded sample data and are waiting on their real backends (#19, #20, #21, and #10.1–#10.5/#11's wishlist/analysis data) before this issue's acceptance criteria are actually met.

### Progress note (2026-08-02)

`components/nav.tsx` is being reworked from one hardcoded global search+Upload
into a per-page slot — each page supplies its own search behavior and action
buttons instead of every route sharing the same ticker-search + CSV-upload
bar (see #10.1 discussion). For `/` (this page): slot = ticker search only,
no action buttons. No dashboard-page code change needed beyond whatever slot
mechanism the nav refactor lands on.

### Acceptance criteria

- [ ] `/` renders bentobox tiles for wishlist, holdings, Docker health, Pi resources, services health, schedules status, and a combined TradingAgents + youn-server update notification tile
- [ ] All tiles call existing API endpoints — no duplicate backend logic introduced in this issue
- [ ] Page auto-refreshes on the same interval as #10.1/#10.4's tables
- [ ] `/wishlist` and `/stocks` remain reachable via nav (no longer the default landing route)

---

## [ ] Issue #23 — Stock Price History Chart (Portfolio)

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #19

### What to build

Per-ticker historical price chart on `/portfolio`, extending the `get_price_history()` service method (already built in #4, currently `period`-only, unused by any route) with the resolution/range this needs, plus a new API route and chart component.

**`FinnhubClient.get_price_history()` (`app/services/stocks.py`):**
- Add `interval` param (`"1h"` / `"1d"` / `"1wk"` / `"1mo"`) — currently hardcoded to yfinance's default daily bars regardless of `period`
- For the `3Y` preset, pass explicit `start`/`end` dates instead of `period` — yfinance's `period` values are `1y`/`2y`/`5y`/`10y`/`ytd`/`max`, no native `3y` string
- `ALL` preset maps to `period="max"`

**Presets (fixed, not free-form interval+range dropdowns — avoids invalid combos like hourly-over-3-years, which Yahoo's data window can't serve anyway):**

| Preset | Interval | Range |
|---|---|---|
| `1M` | hourly | 1 month |
| `1Y` | daily | 1 year |
| `3Y` | weekly | 3 years (via explicit `start`/`end`) |
| `ALL` | monthly | `period="max"` |

Hourly is only offered on the `1M` preset — Yahoo's intraday data window caps `60m`/`1h` bars at roughly the last ~730 days, so hourly-over-1-year or hourly-over-3-years isn't representable through this data source regardless of UI choice.

**`GET /api/market/{ticker}/history?preset=1Y`** (new route, ticker-scoped rather than alert/position-id-scoped — reusable, doesn't require a `StockAlert` or `Position` to exist for the ticker):
- Maps `preset` → the interval/range pair above, calls `get_price_history()`, returns `[{date, close}]`

**`StockHistoryChart` component (`/portfolio`):**
- recharts `LineChart`, same pattern as #10.3's `PriceHistoryChart`
- Preset buttons (`1M` / `1Y` / `3Y` / `ALL`) above the chart, click swaps the active fetch
- Attached per-position — click a holdings-table row to expand, same interaction pattern as #10.3's wishlist row expansion

### Why (context)

`get_price_history()` already exists (#4) but is currently unreachable from any API route — nothing wires it to the frontend. The user wants historical charts on individual portfolio holdings; since `Position` is ticker-based (not alert-based), the new route is scoped by ticker directly rather than nested under `/api/stockalerts/{alert_id}/...`, keeping it reusable for any ticker regardless of whether it also has a `StockAlert` or `Position` row.

Preset buttons (not independent interval+range controls) were chosen specifically to make invalid combinations structurally impossible — mirrors the same design principle used elsewhere in this project (matching known data-source constraints instead of exposing footguns in the UI).

### Acceptance criteria

- [ ] `get_price_history()` accepts `interval`, and either `period` or explicit `start`/`end`
- [ ] `GET /api/market/{ticker}/history?preset=1Y` (and `1M`/`3Y`/`ALL`) returns correctly-shaped price points for each preset
- [ ] `3Y` preset returns real 3-year-range data (not silently falling back to a native yfinance period)
- [ ] `StockHistoryChart` renders on `/portfolio`, attached per-position, preset buttons switch the displayed data
- [ ] Chart follows the same row-expand interaction pattern as #10.3's `PriceHistoryChart`

---

## [ ] Issue #30 — Trending/Popular Assets (Portfolio)

**Type:** feat / AFK
**Estimate:** ~4h
**Blocked by:** #19

### What to build

A single blended top-10 "Popular Assets" list on `/portfolio` — stocks and ETFs mixed together, ranked by volume, not two separate category tabs. Ranking and all displayed numbers sourced from yfinance (free, no key); per-ticker metadata and news sourced from Finnhub REST (free tier, already used elsewhere in this project) rather than yfinance's own unofficial `.news`.

No indices category — an index isn't a tradeable instrument (no order book, no real trading volume of its own; it's a calculated composite of its constituents), so "most active by volume" has nothing to rank. Real exposure to an index goes through the ETFs that track it (e.g. `SPY` for the S&P 500), which do have real volume and already fall under the ETF pool below.

**Live-verified against yfinance 0.2.59 (the version pinned in `requirements.txt`) — 2026-08-02:**

**Stock candidates — confirmed working as planned:**
- `yf.screen("most_actives", count=25)` (over-fetch beyond the final top 10 — see "Blending," below)
- Internally this predefined query is `sortField='dayvolume', sortType='DESC'`, filtered to `region=us`, `intradaymarketcap >= 2B`, `dayvolume > 5M` — confirms "trending" = most-traded, not biggest gainer, is exactly Yahoo's own definition, not something we're approximating
- Response quotes are genuinely real-time, not delayed: live-tested response showed `exchangeDataDelayedBy: 0`, `quoteSourceName: "Nasdaq Real Time Price"` — the "yfinance is 15min-delayed" assumption from earlier planning doesn't hold up as a documented fact for what this endpoint actually returns; it's the generic free-tier-data industry convention, not Yahoo's actual behavior here
- Each quote already carries everything needed for free: `symbol`, `longName`/`shortName`, `regularMarketPrice`, `regularMarketChangePercent`, `regularMarketVolume`, `marketCap`, `quoteType` — no second call

**ETF candidates — the original plan's "open risk" is now confirmed, not hypothetical:**
- Tried `EquityQuery('eq'/'is-in', ['quoteType', 'ETF'])` and the equivalent on `FundQuery` — both raise `ValueError: Invalid field`. `quoteType` is not a filterable field on either class in this version. `EquityQuery`'s only equality-filterable fields are `region`/`exchange`/`peer_group`/`sector`; `FundQuery` is scoped to mutual funds specifically (`categoryname`, `performanceratingoverall`, etc.), not ETFs. There is no query-builder path to "give me only ETFs" — confirmed dead end, not worth retrying.
- **Confirmed fallback works:** a curated static list of ETF tickers, each fetched individually via `yf.Ticker(symbol).info` (one call per ticker — heavier than the single stock screener call, see "Known cost asymmetry" below), sorted by `regularMarketVolume` ourselves since there's no server-side ranking for a hand-picked list.
- **The curated ETF ticker list itself is not yet defined** — only 5 sample tickers (`SPY`, `QQQ`, `VOO`, `IWM`, `VTI`) were used to prove the mechanism works, not a real candidate pool. Needs to be an actual list (10-20+ tickers deep) before this is implementable.

**Field gap found — ETFs don't have `marketCap`:** live-tested `fast_info` and `.info` both return `marketCap: None` for ETF tickers, since a fund isn't a company with shares outstanding to multiply. The equivalent "size" field is `totalAssets` (AUM) — confirmed present via `.info` (e.g. `totalAssets: 781188857856` for SPY). **Decision: use `totalAssets` for ETF rows on the frontend** in whatever field displays "size" — the response schema needs to account for this being a different underlying field per asset type, not one `market_cap` column that means the same thing for both.

**Known cost asymmetry (not yet resolved — revisit when implementing):** stocks cost 1 yfinance call total regardless of how many results come back (`yf.screen()`). ETFs cost 1 heavy `yf.Ticker(x).info` call **per curated candidate** — `.info` is the slow multi-request scrape, not the lightweight `fast_info` (which is cheap but lacks `totalAssets`). If the curated list needs to be 15-20 tickers deep for a meaningful sorted result, that's 15-20 heavy scrape calls every refresh cycle for ETFs alone, vs. 1 call for stocks. Needs an explicit decision at implementation time — smaller curated list, a separate/longer refresh interval for the ETF half, or accepting the cost — rather than assuming the blanket refresh interval below applies equally to both halves.

**Blending:** over-fetch beyond 10 from each side (stock candidates via `count=25` on `most_actives`; ETF candidates from the full curated list), merge both pools, sort the combined set by volume descending ourselves, slice to the final top 10. Each row tagged with `asset_type: "stock" | "etf"` so the frontend can render a category badge per row (no more segmented-control tabs — see below).

**Metadata split (`app/services/stocks.py`, `FinnhubClient`):**
- Company name/logo — Finnhub REST `/stock/profile2` (free tier), one call per ticker in the final blended top 10 (10 tickers, not 20 — one list now, not two separate top-10s)
- News — reuse existing Finnhub `/company-news` (already planned/free elsewhere) rather than yfinance's unofficial `.news` scrape, one call per ticker — also used by `#31`'s ticker detail page News section (same call, fetched once on page load there instead of on this panel's 30s cadence)
- **Live-tested against a real Finnhub key — 2026-08-02, resolves both the tier question and the ETF-support question:**
  - `/stock/profile2?symbol=AAPL` returned full data on this key — **confirmed free tier, not premium-blocked**. (A 2020 Finnhub GitHub issue had said this endpoint moved to premium; that's evidently stale or reversed since — current behavior is what matters, not that historical note.) Response included a working logo URL (`https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/AAPL.png` — PNG for this ticker, format not guaranteed consistent across tickers).
  - `/stock/profile2?symbol=SPY` (ETF) returned **`{}`** — a completely empty object, not an error, not null fields, just nothing. Confirmed: this endpoint has zero data for ETF symbols (no name, no logo, no market cap). Matches the suspicion that a *company* profile endpoint has nothing to say about a fund.
  - `/company-news?symbol=SPY` (ETF), by contrast, **works fine** — 115 real articles came back, same shape/quality as AAPL's 245. News is not broken for ETFs, only the profile call is.
- **Implication for ETF rows:** name comes from yfinance instead (`longName`/`shortName`, already present in the quote payload used for ranking — no gap there). Logo has no source at all for ETFs — Finnhub returns nothing, and yfinance has no logo/image field either (checked `Ticker.info` directly, zero matches for any logo/image/icon-named key). ETF rows keep the existing colored-initial placeholder rather than a real image; only stock rows in the blended list will show a real logo.
- Finnhub stays scoped to name/logo/news only — price/market cap/volume/AUM all come from yfinance, not Finnhub (considered routing price through Finnhub's real-time quote instead, backed off it — no verified freshness gap over yfinance's own numbers for this use case, and it would've added a third Finnhub call per ticker against the free tier's 60-calls/minute cap for no confirmed benefit)

**Refresh:** SWR polling, 30-second interval — same convention as `#10.1`/`#10.4`, not websockets (yfinance has no streaming API; Finnhub's websocket is scoped to `StockAlert`'s fixed user-configured list in `#4`, not a rotating discovery ranking sourced from a different provider). 20 Finnhub calls/refresh (10 tickers × 2 calls) stays comfortably under the 60/min free-tier cap at this interval, server-side-cached and shared across all connected clients rather than one Finnhub round-trip per browser poll — but see "Known cost asymmetry" above, since the yfinance side of a refresh cycle isn't uniformly cheap the way the Finnhub side is.

**`GET /api/market/trending`** (new route, no `category` param — one blended list, not filterable by category):
- Returns `[{ticker, name, price, change_pct, volume, market_cap, total_assets, asset_type, news: [...]}]` — `market_cap` populated for stocks, `total_assets` populated for ETFs, the other left null per row

**`TrendingAssetsPanel` component (`/portfolio`):**
- No segmented control — single table, one blended ranked list
- Table: ticker, name, price, % change (color-coded), size (market cap or AUM depending on `asset_type`), volume, category badge (`Stock`/`ETF`), news-link icon

### Why (context)

Splitting sourcing (yfinance for ranking/quote/history, Finnhub for metadata/news/validation) keeps each provider doing what it's already trusted for elsewhere in this codebase — Finnhub's official REST for anything that needs to be reliable (profile, news), yfinance's unofficial-but-free surface for the bulk/discovery data (screener ranking, quote fields riding along with it, historical bars) that has no free official equivalent. Avoids adding a paid Finnhub tier (movers/screener endpoints are premium-only) just for this feature, and avoids splitting the same displayed numbers (price, market cap, volume) across two providers for no verified benefit.

A single blended list over two category tabs because ranking is fundamentally about volume/activity, and there's no reason that comparison should stop at an asset-type boundary — big ETFs like SPY/QQQ routinely post some of the single highest raw share volumes on US markets, often outranking individual stocks, so a genuine blended-by-volume list plausibly mixes both types rather than being dominated by one.

### Acceptance criteria

- [ ] Curated ETF candidate list defined (not yet — only 5 sample tickers proven to work mechanically)
- [ ] `get_trending_stocks()` returns stock candidates via yfinance `most_actives`, including price/change_pct/market_cap/volume from the same call
- [ ] `get_trending_etfs()` returns ETF candidates from the curated list via per-ticker `.info` calls, including `total_assets`
- [ ] Blended merge produces a single top-10 sorted by volume across both pools, each row tagged with `asset_type`
- [x] Finnhub ETF-support verified live — confirmed 2026-08-02: `/stock/profile2` returns `{}` for ETFs (no logo/name/data), `/company-news` works fine for both. ETF rows use yfinance's name + no logo (placeholder fallback); stock rows use Finnhub's name/logo
- [ ] Each stock row is enriched with Finnhub `/stock/profile2` name/logo; every row (stock and ETF) gets `/company-news` headlines
- [ ] `GET /api/market/trending` returns correctly-shaped blended data
- [ ] `TrendingAssetsPanel` renders on `/portfolio` as a single table (no tabs), auto-refreshes every 30 seconds

---

## [x] Issue #31 — Ticker Detail Page (Market Details Navigation)

**Type:** feat / AFK
**Estimate:** ~7h
**Blocked by:** #19, #23, #30, #33

### What to build

A dedicated per-ticker page — `/market/[ticker]` (ticker-scoped, same convention as #23's `GET /api/market/{ticker}/history`: reusable for any ticker regardless of whether it also has a `Position` or `StockAlert` row). Reachable from four places:
- Popular Assets' "View Details" button (`TrendingAssetsPanel`, #30, `/portfolio`)
- Each Holdings row (`HoldingsTable`/holdings list, #19, `/portfolio`)
- Each Watchlist row (stock watchlist list, `/portfolio`)
- Ticker search in `Nav` (`components/nav.tsx`) — top-right, next to the Home/Portfolio/Watchlist links, app-wide rather than scoped to `/portfolio` (any page can want to jump to a ticker). **Already built ahead of this issue**, as a cmdk-backed expanding search with a real results dropdown (`handleSelect` navigates via `router.push('/market/{TICKER}')` on selection) — ahead of where the old plain-`Input`-plus-submit-on-Enter description here used to have it. Still doesn't call `validate_ticker` (no backend yet), so an invalid symbol still navigates unconditionally today. Wiring that check, plus retrofitting onto the shared `SearchBar` component in `navigate` mode, is this issue's remaining scope on the nav side.

The first three currently render as plain (non-linked) rows/cards — wiring real navigation means turning each into a `Link`/`onClick` to `/market/{ticker}`, done as part of this issue rather than #19/#23/#30 themselves.

Layout confirmed against a real Wealthsimple reference screenshot (SOFI, 2026-07-29) — see `frontend.md`'s `/market/[ticker]` section for the full field inventory. Summary:

**Page sections, always shown:**
1. Header — logo, ticker, company name
2. Price block — current price + currency, $ and % change over the selected chart period
3. `MarketDetailChart` — line chart, presets `1D`/`1W`/`1M`/`3M`/`6M`/`YTD`/`1Y`/`10Y`, "Markets closed" status indicator. **New, separate component** from #23's `StockHistoryChart` (`1M`/`1Y`/`3Y`/`ALL`) — different context (dedicated full page vs. an inline holdings-row expand), different range needs; matches the existing precedent in `frontend.md` for keeping chart components separate rather than forcing one shared abstraction across different use cases.
4. `MarketDetailsPanel` — Open, Bid + quote size, Ask + quote size, Last sale (price only), High, Low, Volume, Average volume, 52-week high, 52-week low, Exchange
5. `FinancialsPanel` — Market cap, Shares outstanding, P/E ratio
6. `AboutPanel` — company description (yfinance `longBusinessSummary`), shown in full — no truncation/"Show more"

**Conditional, only when the ticker has dividend data** (`dividendYield`/`dividendRate` not null):
7. `DividendsPanel` — Frequency, 12-month yield, Ex-dividend date, Expected payment date. SOFI (the reference) pays no dividend and Wealthsimple's own UI omits the panel entirely rather than showing empty fields — same behavior here.

**Conditional, only when a `Position` exists for the ticker (shares > 0):**
8. Chart reference-price overlay — dashed horizontal line at the price of the most recent buy tranche (from `Activity`, #33 — latest `transactionDate`, not the position's weighted `avg_cost`; falls back to `avg_cost` if no matching `Activity` row exists), vertical marker + dot at that tranche's date, floating $ label — layered onto `MarketDetailChart`
9. `PositionSummaryCard` — "Stocks" header + `1D`/`All` toggle; share count, currency, allocation %, qty, current price, total value, all-time return

**Conditional, independent check — only when `Activity` rows (#33) exist for the ticker** (a fully-sold position has no current `Position` but should still show trade history):
10. `RecentActivityPanel` / `RecentActivityCard` — see scope note below, and `frontend.md` for the full field-mapping/gap table against #33's confirmed CSV shape

**`get_market_details(ticker)` (`app/services/stocks.py`):**
- Single yfinance `Ticker(ticker).info` call sources sections 4–7 in one shot (bid, ask, open, dayHigh/Low, volume, averageVolume, fiftyTwoWeekHigh/Low, exchange, marketCap, sharesOutstanding, trailingPE, dividendYield, dividendRate, exDividendDate, longBusinessSummary) — none of this is available on Finnhub's free tier (bid/ask/52-week/financials/dividends are Finnhub premium-only), so unlike #30's split, this endpoint is yfinance-only. Same instability caveat already documented for yfinance elsewhere applies here too.
- Company name/logo stays on the existing Finnhub `/stock/profile2` call (already planned in #30) for the header, rather than duplicating via yfinance, to avoid two sources for the same fact.

**Backend caching (added 2026-08-12):** `get_market_details()` gets its own short in-memory TTL cache (`{ticker: (details, fetched_at)}`, separate dict from `#19`'s `get_price()` cache — different call, different shape), TTL maybe 30-60s rather than `get_price()`'s 10-15s, since these fields (bid/ask/52-week/financials) don't move tick-to-tick the way a live price does. Matters more here than for `get_price()`: the underlying `Ticker(ticker).info` call is `#30`'s own words "the slow multi-request scrape" (`issues.md`'s `#30` section, "Known cost asymmetry") — the heaviest single call in this app's price-data surface, worth protecting from duplicate hits (multiple tabs on the same ticker's detail page, or a ticker landed on via more than one of the four navigation entry points in close succession) more than any of the cheaper REST calls.

**`GET /api/market/{ticker}/details`** (new route): returns the bundled dict above.

### Scope notes (things that don't map cleanly)

- **Margin requirement** (shown in the reference screenshot): **dropped**. It's a brokerage house rule, not market data — no field for it exists on Finnhub or yfinance, and this app doesn't execute trades or extend margin. Not applicable to a self-hosted read-only tracker.
- **Last-sale trade size** (the "x 5,000" in the reference — distinct from bid/ask size, which stays): **dropped**. Neither provider's free tier has it — yfinance's `Ticker.info` has no last-trade-size field, and Finnhub's free `/quote` REST returns price/high/low/open/previous-close only (bid/ask/size sit behind Finnhub's paid plan). The only free-tier path to trade size on either provider is Finnhub's WebSocket trade stream (already used for `StockAlert` price ticks, #4) — a live feed you'd have to keep connected and cache the latest print from, not worth the lift for one field. Bid/ask **+ size** stay in scope since yfinance does carry those (with the usual free-tier flakiness caveat already noted above).
- **"Explore options trading" promo card and "Download trade confirmation" button** (both shown in the reference): **dropped**, same reasoning as margin requirement — Wealthsimple-specific upsell/document-generation features with no equivalent in a read-only tracker.
- **Recent activity**: **no longer an open design decision** — resolved once #33 landed. Originally this note assumed a new `Position`/`StockAlert` mutation-audit table would be needed since none existed; instead, #33's `Activity` model (populated from the Wealthsimple CSV import) is a real transaction history and is what `RecentActivityCard` renders directly, filtered by ticker. The reference screenshot's expanded card (Account, Status, Submitted, Filled, Trading session, Type, Limit price, Entered/Filled quantity, Exchange rate, Total cost) doesn't map 1:1 onto the confirmed CSV columns, though — several fields have to be approximated or omitted. Full field-by-field gap table is in `frontend.md`; headline gaps:
  - No order status in the CSV → hardcode "Completed" (activity exports only contain settled transactions)
  - No time-of-day, only dates → Submitted/Filled show date only
  - No trading-session field → omit
  - `activity_sub_type` so far only observed as `BUY` in the one sample file on hand; expected real values per Wealthsimple's actual order types: `MARKET_BUY`, `LIMIT_BUY`, `STOP_LIMIT_BUY`, `STOP_MARKET_BUY`, `RECURRING_BUY` — literal enum strings unconfirmed until a export containing one of these is seen
  - No captured *limit* price (only the execution price via `unit_price`) → omit the limit-price row, or show only the filled price, for limit-type orders
  - FX rate isn't a structured column — it's embedded as free text inside `description` (e.g. `"...FX Rate: 1.4510"`) and needs regex extraction during import; rows for CAD-hedged instruments have no FX rate text since no conversion happens

### Why (context)

yfinance's `Ticker.info` already returns nearly every field the mockup needs in a single call, whereas Finnhub's free tier covers almost none of it (those fields sit behind Finnhub's paid plan) — so this endpoint breaks from the usual "Finnhub for anything that needs to be reliable" split purely because Finnhub's free tier doesn't offer an alternative here.

A separate chart component (rather than extending #23's `StockHistoryChart` with more presets) follows the same reasoning already used for `StockHistoryChart` vs `PriceHistoryChart`: different page context, different controls, not worth forcing a shared abstraction.

### Acceptance criteria

- [x] `get_market_details(ticker)` returns the bundled fields via yfinance `Ticker.info`
- [x] `GET /api/market/{ticker}/details` returns correctly-shaped data
- [x] `/market/[ticker]` renders all always-shown sections; `DividendsPanel` only when dividend data exists
- [x] Chart reference-price overlay (latest buy tranche) and `PositionSummaryCard` render only when a `Position` exists for the ticker (shares > 0)
- [x] `RecentActivityPanel` renders only when `Activity` rows (#33) exist for the ticker, independent of whether a current `Position` exists (fully-sold tickers still show history)
- [x] `RecentActivityCard` expands/collapses per row and renders the approximated fields per the gap table above, without fabricating data the CSV doesn't provide
- [x] Popular Assets' "View Details", each Holdings row, and each Watchlist row all navigate to `/market/{ticker}`
- [x] `Nav`'s ticker search validates the entered ticker via `validate_ticker` before navigating; shows an error rather than navigating on an invalid symbol (currently navigates unconditionally)
- [ ] `MarketDetailChart` presets (`1D`–`10Y`) fetch and render correctly, independent of #23's `StockHistoryChart`
- [ ] "Notify me" creates a `StockAlert` for the viewed ticker via `POST /api/stockalerts`, `run_analysis` toggle included
- [ ] `get_market_details()` results are cached in-memory (~30-60s) — confirmed via two near-simultaneous requests for the same ticker producing only one `Ticker(ticker).info` call
- [ ] "Run TradingAgents" works on any ticker regardless of alert/holding/watchlist status, via `#35`'s `POST /api/analysis/{ticker}`
- [ ] "View recent analysis report" is hidden when no `AnalysisResult` exists for the ticker; once one exists, shows the most recent result's status/JSON viewer, with older runs for the same ticker still reachable in the same section
- [ ] News section renders headline/image/source/summary/link per article via Finnhub `/company-news`, fetched once on page load (works for both stocks and ETFs)

### Implementation notes (added 2026-08-02, during #30 planning)

- **Logo**: not part of `get_market_details()` — yfinance has no logo field at all (confirmed live). Header logo renders the same static Finnhub URL as `#19`/`#30` (`<img src=".../stock_logo/{ticker}.png">`, unauthenticated, no backend call), with the existing colored-placeholder fallback for ETFs/misses.
- **Live price while viewing**: REST fetch on page load + normal poll cadence (same convention as `#10.1`/`#10.4`/`#30`), not websocket. Considered temporarily subscribing the viewed ticker on `FinnhubClient`'s websocket for the duration of the page view; backed off — adds subscribe/unsubscribe lifecycle complexity tied to page mount/unmount, and competes with `#19`'s `Position`/`StockAlert` tickers for the free tier's shared ~50-symbol cap, for a "reading about a stock" use case that doesn't need sub-second freshness. If the viewed ticker happens to already be a `Position`/`StockAlert` ticker (already subscribed for other reasons), it incidentally benefits from the live cache too — a side effect, not something designed around.
- **"Notify me" / "Run TradingAgents" buttons (added 2026-08-02):** header gets two new actions, both enabled for any ticker regardless of whether it's a current holding/watchlist item:
  - **"Notify me"** — opens an inline quick-create form (target price, direction, `run_analysis` toggle) and calls the existing `POST /api/stockalerts` (`#8`), no new backend needed. If `run_analysis` is enabled, the already-built automatic path (`#7`/`#9`) takes over from there on threshold crossing — no page-level wiring beyond creating the alert.
  - **"Run TradingAgents"** — always enabled, any ticker, no alert required. Calls `#35`'s `POST /api/analysis/{ticker}`, not `#9`'s alert-scoped route (which structurally can't run without a `StockAlert` id).
  - **"View recent analysis report" (refined 2026-08-02):** conditionally rendered — hidden entirely if `GET /api/analysis/{ticker}` (`#35`) returns zero results for this ticker, so pages for never-analyzed tickers don't show an empty section. Once at least one result exists, surfaces the most recent one prominently: status badge if `pending`/`running` (nothing to view yet, matches `#11`'s pattern), collapsible JSON viewer if `done`. Older runs for the same ticker (if any) stay accessible within this same section — `GET /api/analysis/{ticker}` already returns full per-ticker history in one call, no separate request or link out to `#11`'s global page needed.
- **News section (added 2026-08-02):** new panel — headline, image, source, summary, link, per article — sourced from Finnhub `/company-news` (`FinnhubClient`), the same call `#30` already plans per ticker in its blended list. Confirmed live-tested working for both stocks and ETFs (`#30` planning session: 245 articles for AAPL, 115 for SPY, same shape/quality either way) — not a new endpoint to validate, just a new consumer of one already confirmed to work. Fetched once on page load alongside `get_market_details()`, not polled — news doesn't change fast enough to need `#30`'s 30s cadence, consistent with how the rest of this page's yfinance-sourced panels already work (fetch-once, no refresh loop).

---

## [ ] Issue #38 — Earnings Calendar (Portfolio Page + Ticker Detail Page)

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #19, #31

### Why (context)

Surfaced while comparing Finnhub vs. yfinance for earnings-date data. Finnhub's `/calendar/earnings` REST endpoint (already the app's Finnhub REST client, `services/stocks.py`) returns `date`, `year`/`quarter`, `epsEstimate`/`epsActual`, `revenueEstimate`/`revenueActual`, and `hour` (`bmo`/`amc`/`dmh`) — actual fields `null` until reported. Chosen over yfinance's `get_earnings_dates()` (EPS-only, no revenue fields, no explicit quarter/year, and carries the same unofficial-scrape reliability caveat already documented for yfinance elsewhere in this repo) — matches the existing "Finnhub for anything that needs to be reliable" split already established by `#30`/`#31`.

Two surfaces, both in scope for this issue rather than split across two:
1. **Portfolio-level widget** (`/portfolio`) — glanceable "upcoming earnings" list across current holdings, soonest-first.
2. **Per-ticker panel** (`/market/[ticker]`, `#31`) — same pattern as that page's existing conditional panels (`DividendsPanel`, `PositionSummaryCard`) — extends an already-shipped (`✅ Done`) page rather than duplicating it.

### What to build

- `get_earnings_calendar(tickers: list[str])` (`app/services/stocks.py`) — Finnhub `/calendar/earnings` call, filtered to the tickers passed in
- `GET /api/portfolio/earnings` (new route) — calls the above with all current `Position` (`#19`) tickers, returns upcoming entries sorted soonest-first
- `GET /api/market/{ticker}/earnings` (new route) — same underlying call, single ticker, both upcoming and recent-past (for the detail page's "last reported" context)
- Portfolio widget: ticker, date, `hour` badge (before/after market), `epsEstimate` (and `epsActual` once populated)
- `EarningsPanel` on `#31`'s ticker detail page — same conditional-panel convention as `DividendsPanel` (only rendered when Finnhub actually returns an entry for that ticker), next reported date + last reported date/estimate-vs-actual if available

### Acceptance criteria

- [ ] `/portfolio` shows an upcoming-earnings widget listing all held positions with a known upcoming earnings date, soonest first
- [ ] Widget shows date, before/after-market timing, and EPS estimate per entry
- [ ] `/market/[ticker]` shows an `EarningsPanel` for tickers with earnings data, following the same conditional-render convention as `DividendsPanel`
- [ ] A ticker with no earnings data available (delisted, ETF, etc.) shows no panel/widget entry, not an empty section
- [ ] Verify actual free-tier access to `/calendar/earnings` against the app's real `FINNHUB_API_KEY` before relying on it — tier limits weren't confirmed during planning, only the response shape

---

## Group 9 — AI Chat

Kept separate from Group 4 (AI Analysis) deliberately — Group 4 is the TradingAgents subprocess integration (triggered automatically on stock threshold events); this group is a distinct, user-initiated feature: chatting about a specific report after the fact. Different trigger model, different auth model (Pro-plan/OAuth rather than TradingAgents' own API-key config), no shared code path.

---

## [ ] Issue #25 — Claude OAuth Auth Working in Docker

**Type:** feat / AFK
**Estimate:** ~1h
**Blocked by:** None — can start immediately

### What to build

Makes Pro-plan/subscription auth (via `ant auth login`) actually usable from inside the backend's Docker container, and removes the dead API-key config that was never wired up.

- Mount `~/.config/anthropic/` (the OAuth profile `ant auth login` creates on the host) into the backend service in `docker-compose.yml` — same pattern already used for TradingAgents' `/opt/tradingagents` volume
- Verify a bare `Anthropic()` client call succeeds *from inside the running container*, with no `ANTHROPIC_API_KEY` set anywhere — confirms the mounted profile is actually being picked up, not just working coincidentally on the host
- Delete `anthropic_api_key` from `backend/app/core/config.py` — declared but has zero usages anywhere in the backend; leaving it in place implies a code path that doesn't exist and invites accidentally wiring up metered API-key billing instead of the intended Pro-plan auth

### Why (context)

Without the volume mount, the container has no way to see the host's OAuth login at all — the whole Pro-plan-auth approach would work when tested locally outside Docker and then silently fail (or fall back to no auth) the moment it actually runs in the deployed container. Catching this now, as its own isolated infra step, means #26 can be built and tested against working auth from the start instead of debugging two new things (chat logic *and* auth plumbing) at once.

### Acceptance criteria

- [ ] `~/.config/anthropic/` is mounted into the backend container in `docker-compose.yml`
- [ ] A test call via a bare `Anthropic()` client succeeds from inside the container with no `ANTHROPIC_API_KEY` env var set
- [ ] `anthropic_api_key` removed from `backend/app/core/config.py`

---

## [ ] Issue #26 — Per-Report Chat Backend (Non-Streaming)

**Type:** feat / AFK
**Estimate:** ~4h
**Blocked by:** #8, #25

### What to build

Lets the user hold a multi-turn conversation about one specific `AnalysisResult` (TradingAgents stock report). The Claude Messages API is stateless — this is entirely what makes "continuing a conversation" work at all; see `keynotes.md`'s "Claude API statelessness" entry for why there's no shortcut here.

**Model — new `ChatMessage` table:**
- `id`, `analysis_result_id` (FK → `analysis_results`, `ondelete="CASCADE"`), `role` (`"user"` | `"assistant"`), `content` (Text), `created_at`
- New Alembic migration, numbered sequentially after the existing `0001`–`0008` migrations

**`POST /api/analysis-results/{id}/chat`** — body `{message: str}`. Per turn:
1. Load the `AnalysisResult` (404 if missing), read the report file off disk via `report_path` (a pointer per `architecture.md`'s design — the DB never stores report content, only the path into the TradingAgents volume)
2. Load all prior `ChatMessage` rows for this `analysis_result_id`, ordered by `created_at` → build the full `messages` array
3. Append the new user message, call Claude
4. Persist both the new user message and Claude's reply as new `ChatMessage` rows
5. Return the reply

**Claude call specifics:**
- `model: "claude-opus-5"`, `thinking: {type: "adaptive"}`
- Report content goes in a `system` block with `cache_control: {type: "ephemeral"}` — stable across every turn in one thread, only `messages` grows per turn, so repeat turns in the same conversation don't re-pay full input cost for the whole report
- Auth via a bare `Anthropic()` client (relies on #25's mounted OAuth profile) — not the deleted `anthropic_api_key` field

### Why (context)

See `keynotes.md`'s "Claude API statelessness — authentication ≠ conversation memory" entry for the full reasoning: switching to OAuth/Pro-plan auth (#25) has no bearing on whether the API remembers prior turns — it doesn't, regardless of auth method — so this `ChatMessage` table and the load/append/persist cycle above is the only way this feature can work, not a stopgap.

Non-streaming deliberately first — the full round trip (persistence, Claude call, caching) is the real complexity here; streaming (#27) is a transport enhancement layered on top once the underlying exchange already works.

### Acceptance criteria

- [ ] `ChatMessage` model + migration created, cascades on `AnalysisResult` deletion
- [ ] `POST /api/analysis-results/{id}/chat` returns 404 for a missing `AnalysisResult`
- [ ] A second message in the same thread produces a reply that reflects context from the first turn (proves persistence + history-passing actually works, not just that the endpoint responds)
- [ ] Report content is sent in a cached `system` block, not resent as part of `messages`
- [ ] Both the user message and Claude's reply are persisted as new `ChatMessage` rows after each turn

---

## [ ] Issue #27 — Streaming Chat Responses

**Type:** feat / AFK
**Estimate:** ~1.5h
**Blocked by:** #26

### What to build

Converts `POST /api/analysis-results/{id}/chat`'s response to a stream (SSE) so replies render progressively instead of arriving all at once.

### Why (context)

One-directional server-push, the same shape already documented in `keynotes.md`'s polling-vs-push section — a genuine SSE fit, not a stretch. Kept separate from #26 since it's a transport change, not new functionality; #26 is fully demoable and useful on its own without it.

### Acceptance criteria

- [ ] `POST /api/analysis-results/{id}/chat` streams the reply incrementally rather than returning it as one block
- [ ] Persistence behavior from #26 (both messages saved after the turn completes) is unchanged

---

## [ ] Issue #28 — Chat UI

**Type:** feat / AFK
**Estimate:** ~3h
**Blocked by:** #27, #11

### What to build

The actual chat interface attached to a report: sending messages, showing the running thread, rendering streamed replies as they arrive. Exact placement within #11's Analysis Results UI is intentionally undecided here — #11 doesn't exist yet, and forcing a placement decision before that page exists would be guessing.

### Acceptance criteria

- [ ] User can send a message and see it appear in the thread immediately
- [ ] Claude's reply renders progressively as it streams in
- [ ] Reloading the page (or revisiting later) shows the full prior thread for that report, not just the current session

---

## [ ] Issue #32 — Wealthsimple CSV Upload Trigger (Frontend Stub)

**Type:** feat / AFK
**Estimate:** ~1h
**Blocked by:** none

### What to build

An icon button on the Holdings tile (`/portfolio`) that opens the OS file picker scoped to `.csv`, same interaction pattern as Watchlist's "Add item" plus-button. Selecting a file just captures the `File` object client-side and shows the selected filename back to the user (e.g. small label near the button) — no parsing, no upload request, no backend call. Purely the entry point, staged ahead of #33's actual import pipeline.

### Why (context)

User wants to import Wealthsimple account activity CSV exports (sample confirmed 2026-07-29, see #33) so portfolio holdings stop requiring fully manual entry. Backend storage/parsing (#33) isn't designed yet — building the upload trigger first lets the interaction land now without blocking on backend schema decisions.

### Acceptance criteria

- [ ] Icon button visible on the Holdings tile
- [ ] Clicking it opens the OS file picker restricted to `.csv`
- [ ] Selecting a file displays its filename in the UI
- [ ] No network request or parsing happens yet — purely local file selection

---

## [ ] Issue #33 — Wealthsimple Activity Import (Parse & Persist)

**Type:** feat / AFK
**Estimate:** ~6h
**Blocked by:** #19, #32

### What to build

Backend pipeline that turns an uploaded Wealthsimple "activities export" CSV into durable `Activity` rows, which `Position` (#19) aggregates get computed from — so re-uploading a fresh export after every trade keeps holdings in sync without manual re-entry.

**Confirmed CSV shape** (sample file, 2026-07-29 export): header row `transaction_date,settlement_date,account_id,account_type,activity_type,activity_sub_type,description,direction,symbol,name,currency,quantity,unit_price,commission,net_cash_amount`, followed by data rows, followed by a blank line and a trailing footer line `"As of <timestamp> GMT-04:00"` that must be skipped during parsing. Two `activity_type` values observed:
- `Trade` (`activity_sub_type: BUY`, `direction: LONG`) — has `symbol`/`name`/`quantity`/`unit_price`; these are the rows that feed Position shares/avg_cost. Only `BUY` has been observed in the one sample file on hand; expected additional real-world values per Wealthsimple's actual order types (used elsewhere in the account but not yet present in a sample export): `MARKET_BUY`, `LIMIT_BUY`, `STOP_LIMIT_BUY`, `STOP_MARKET_BUY`, `RECURRING_BUY`, plus presumably `SELL` variants — literal enum strings unconfirmed, validate parsing against those once a matching export is available rather than assuming the current single-value handling generalizes.
- `MoneyMovement` (`activity_sub_type: EFT` or `E_TRFIN`) — no `symbol`/`quantity`/`unit_price`, just a cash `net_cash_amount` (deposits/e-Transfers). Recorded but not applied to any Position.

FX rate isn't a structured column — for cross-currency buys it's embedded as free text inside `description` (e.g. `"...FX Rate: 1.4510"`); rows for CAD-hedged instruments (e.g. an AVGO CDR) have no FX rate text since no conversion happens. Extract it via regex at import time and store it structured (see `fx_rate` below) rather than re-parsing `description` every time it's displayed — #31's `RecentActivityCard` needs this as a plain field.

**`Activity` model** (new): one row per CSV line — `id`, `transaction_date`, `settlement_date: date | None`, `account_id`, `account_type`, `activity_type`, `activity_sub_type`, `description`, `direction: str | None`, `symbol: str | None`, `name: str | None`, `currency`, `quantity: float | None`, `unit_price: float | None`, `fx_rate: float | None` (parsed from `description` at import time, see above), `commission: float`, `net_cash_amount: float`, `created_at`. New Alembic migration, following the existing numbered-revision convention in `backend/alembic/versions/`.

**`POST /api/activities/import`** (new route, `app/api/activities.py`): accepts multipart `UploadFile`, parses CSV server-side, skips the footer line, inserts rows. Dedups on a composite key (e.g. `transaction_date` + `account_id` + `symbol` + `net_cash_amount`) so re-uploading an export with overlapping date ranges doesn't double-insert — Wealthsimple's export tool doesn't guarantee non-overlapping windows between exports.

**Position sync:** `Trade`/`BUY` activities update the matching `Position` row's `shares`/`avg_cost` (weighted-average cost on each new buy) in the same transaction as the import, creating the `Position` if it doesn't exist yet for that ticker.

**Frontend:** wire #32's file input `onChange` to `POST` the selected file via `FormData` to `/api/activities/import` instead of just displaying the filename; show import result (rows added, rows skipped as duplicates).

### Why (context)

Wealthsimple has no official API (see #19's rejection of direct API integration over ToS/account-lockout risk). CSV export is user-initiated, not scraping, so it sidesteps that risk while still automating away manual position bookkeeping. Chose persist-and-recompute over a stateless parse-only preview: durable across repeated monthly uploads, and Position stays in sync automatically rather than requiring the user to retype numbers from a preview table every time.

### Acceptance criteria

- [ ] `Activity` model + migration created, matching confirmed CSV column shape
- [ ] `POST /api/activities/import` parses a real Wealthsimple export (including trailing footer line) without error
- [ ] Re-uploading an export with overlapping rows does not create duplicate `Activity` rows
- [ ] `Trade`/`BUY` rows update or create the matching `Position`'s shares/avg_cost correctly
- [ ] `MoneyMovement` rows are stored but do not affect any `Position`
- [ ] `fx_rate` is correctly parsed from `description` for cross-currency rows and left `None` for CAD-hedged rows with no FX text
- [ ] Frontend upload button (#32) triggers the import and shows a result summary

---

## [x] Issue #34 — DNS-Based Ad Blocking (Pi-hole)

**Type:** ops / HITL
**Estimate:** ~1h (actual: ~1h, matched estimate)
**Blocked by:** None

### What was built

Deployed **Pi-hole** (chosen over AdGuard Home — see rationale below) as
a new Docker container on the Pi (model 4B, not 5 as originally assumed
— ticket text corrected), alongside the existing youn-server services,
added to the same `docker-compose.yml`.

- `pihole` service added to `docker-compose.yml` (image
  `pihole/pihole:2026.05.0`, pinned rather than `latest`), following the
  `docker-compose.local.yml` convention (pinned tag, named volume,
  restart policy) rather than backend/frontend's `build:` pattern
- DNS on `53/tcp` + `53/udp`, admin UI on `8081` (avoids colliding with
  frontend's `3000` / backend's `8000`)
- `FTLCONF_webserver_api_password` used (current v6 syntax) instead of
  the deprecated `WEBPASSWORD`; `FTLCONF_dns_listeningMode: all` set
  since this runs on default bridge networking, not `--net=host`
- `PIHOLE_WEBPASSWORD` documented in `.env.example` (placeholder only)
- Blocklists: default StevenBlack list (99,558 domains) + hagezi "Pro"
  supplemental list (215,439 domains) — **314,997 unique domains
  blocked total**. Added via the local REST API directly (`pihole api`
  CLI only supports GET in v6; POST required authenticating with
  `curl` against `/api/auth` → `/api/lists`)
- **HITL, done:** Pi's LAN IP (`<pi-lan-ip>`) reserved in the Eero app
- **HITL, done:** Eero's Custom DNS pointed at `<pi-lan-ip>` (IPv4 primary
  only — IPv6 fields left blank since the Pi's IPv6 addresses are
  dynamic/privacy-extension and unsafe to pin; accepted minor gap, see
  `.plan/34-pihole-dns-ad-blocking/challenges.md`)

**Deployment note:** the Pi didn't have the repo cloned yet at the time
(#13 full deployment not done). Set up a read-only GitHub deploy key on
the Pi, cloned the repo to `~/projects/youn-server`, and ran
`docker compose up -d pihole` only — `backend`/`frontend` were left
untouched since their `.env` secrets aren't set up on the Pi yet.

**Pi-hole vs. AdGuard Home (decided during planning):** AdGuard Home has
slightly better default block rates (broader out-of-box lists) and
built-in DoH/DoT, but Pi-hole has the most prior art for "Docker on
Raspberry Pi" specifically, and the default-list gap closes with one
added list (hagezi Pro, as above). Neither tool can block YouTube's
in-video ads — confirmed as a hard limitation (YouTube serves ads from
the same domains as the video itself; blocking would break playback,
not just the ad) — documented, not treated as a defect.

### Why (context)

Network-wide ad/tracker blocking without per-device browser extensions.
Runs on the Pi rather than the Synology NAS to keep the existing
architecture boundary intact — Pi hosts all Docker services, NAS stays
scoped to Postgres + Plex. Unrelated to youn-server's own feature set;
included here since it shares the same host and deployment pattern as
the rest of the Pi's Docker stack.

### Acceptance criteria

- [x] Pi-hole container running on the Pi, added to `docker-compose.yml`
- [x] Admin web UI reachable on the LAN (`http://<pi-lan-ip>:8081/admin`)
- [x] Router's DHCP DNS setting points at the Pi's LAN IP
- [x] A known ad-serving test page shows ads blocked on a test device —
      `https://adblock.turtlecute.org` (the ticket's originally-linked
      d3ward test page is archived/dead): **128/132 blocked (97%)**
- [x] Normal (non-blocked) domains still resolve correctly — verified
      via `dig` and manual browsing (email, bank, news) — no DNS
      breakage for the rest of the network

Full implementation log: `.plan/34-pihole-dns-ad-blocking/`

---

## [ ] Issue #35 — Ticker-Scoped Manual Analysis Trigger (Any Ticker, No Alert Required)

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #9

### What to build

`#9`'s manual trigger (`POST /api/stockalerts/{id}/analyze`) requires a `StockAlert` row's own database id — structurally can't run on a ticker that has no alert. This adds an **additive** ticker-keyed path alongside it, not a replacement, so `#9`'s already-shipped routes stay untouched.

- **Migration**: `AnalysisResult.stock_alert_id` becomes nullable (populated when created via an alert — automatic threshold-crossing or otherwise; null when triggered ad-hoc by ticker). Add `AnalysisResult.ticker: str` (`NOT NULL`, always populated regardless of path) — new Alembic migration, following the existing numbered-revision convention.
- **`POST /api/analysis/{ticker}`** (new route): manual trigger, no `StockAlert` required. Returns 409 if an `AnalysisResult` with `status IN ("pending", "running")` already exists for this ticker — same guard `#9`'s route already has, just correctly ticker-scoped now instead of implicitly relying on alert-id uniqueness. Creates `AnalysisResult { ticker, stock_alert_id: null, status: "pending" }`, spawns `run_analysis()` (reused from `#9`, unchanged), returns 202 immediately — same behavior/shape as `POST /api/stockalerts/{id}/analyze`, just keyed by ticker instead of alert id.
- **`GET /api/analysis/{ticker}`** (new route): all `AnalysisResult` rows for a ticker, `ORDER BY created_at DESC`, regardless of whether `stock_alert_id` is null or set. Supersedes `GET /api/stockalerts/{id}/analysis` for any new UI work, since that older route can't represent a ticker that never had an alert.
- **`GET /api/analysis`** (new route, no ticker filter): all `AnalysisResult` rows across every ticker, `ORDER BY created_at DESC` — feeds `#11`'s global history view (see below).

### Why (context)

Surfaced while placing a "Run TradingAgents" button on `#31`'s ticker detail page — that page is reachable for any ticker (search, Popular Assets, holdings, watchlist), not just ones with an existing `StockAlert`, but `#9`'s route can't run against a ticker with no alert. Kept `#9`'s existing routes untouched rather than retroactively rewriting already-shipped, already-checked-off work — this is purely additive. The automatic path (`StockAlert.run_analysis = true` + threshold crossed → auto-analyze) needed no changes at all; it already works exactly as `#7`/`#9` built it.

### Acceptance criteria

- [ ] Migration adds `AnalysisResult.ticker` (`NOT NULL`) and makes `stock_alert_id` nullable
- [ ] `POST /api/analysis/{ticker}` creates an ad-hoc `AnalysisResult` (no `StockAlert` required), returns 202, spawns analysis
- [ ] `POST /api/analysis/{ticker}` returns 409 if already pending/running for that ticker
- [ ] `GET /api/analysis/{ticker}` returns all results for a ticker regardless of `stock_alert_id`
- [ ] `GET /api/analysis` returns all results across all tickers, unfiltered
- [ ] Existing `#9` routes (`/api/stockalerts/{id}/analyze`, `/api/stockalerts/{id}/analysis`) continue working unmodified

---

## [ ] Issue #39 — Resolve Redirects Before `RETAILER_MAP` Routing (Shortlink Support)

**Type:** fix / AFK
**Estimate:** ~1.5h

### What to build

`_resolve_retailer_and_scraper_type` (`backend/app/api/items.py`) checks `RETAILER_MAP` against the hostname of the **raw input URL**, before any network request happens — so a shortlink (`a.co`, `amzn.to`, or any other retailer's shortener) never matches its real destination's entry, even when that destination is a registered domain with a dedicated scraper.

Change the routing order: resolve the URL's final destination first (a redirect-following `HEAD`, or a lightweight `GET`, via `httpx` with `follow_redirects=True`), **then** check `RETAILER_MAP`/derive the retailer display name against the resolved hostname, not the original one. Applies to both `create_item`'s bulk probing and `create_listing`'s single-URL path, since both share `_resolve_retailer_and_scraper_type`.

### Why (context)

Surfaced testing `#10.2`'s add-item flow with a real `https://a.co/d/...` Amazon shortlink — it failed to scrape entirely, reported in the bulk-create response's `failed[]`. Root-caused live: the redirect itself resolves fine (`httpx` with `follow_redirects=True` reaches the real `amazon.ca` product page, `200 OK`, real HTML) — the failure is that `RETAILER_MAP` lookup happens before that resolution, so the shortlink never gets routed to `AmazonCAScraper` (the only scraper that can actually extract Amazon's price — confirmed the generic extraction hierarchy finds nothing on Amazon's real markup even with a valid fetch). Hardcoding known shortlink domains (`a.co`, `amzn.to`, ...) into `RETAILER_MAP` was considered and rejected — doesn't generalize to other retailers' shorteners, whack-a-mole. Resolving first is the general fix, works for any retailer's shortlink without a hardcoded list.

**Real cost, stated plainly**: this adds one network round-trip to routing for *every* URL added, not just shortlinks — currently, `RETAILER_MAP`-known domains skip probing entirely (the fast path this issue's redirect-resolution step would now precede). Worth confirming the added latency is acceptable before building, given this app's low request volume.

### Acceptance criteria

- [ ] Adding a real Amazon shortlink (`a.co`/`amzn.to`) routes to `AmazonCAScraper` and successfully extracts a price, same as pasting the resolved `amazon.ca` URL directly
- [ ] Retailer display name derives from the resolved hostname, not the shortlink's own domain (e.g. shows "Amazon", not "a_co")
- [ ] A URL that doesn't redirect at all (already the final destination) behaves identically to today — no regression for the common case
- [ ] `create_listing` (single-URL add, sheet's "add retailer" flow) gets the same fix — not just bulk `create_item`

---

## [ ] Issue #40 — Start Patchright's Browser at App Startup

**Type:** fix / AFK
**Estimate:** ~30min

### What to build

`PatchrightScraper.start_browser()`/`close_browser()` (`backend/app/services/scraper/patchright_scraper.py`) are fully implemented but never called anywhere in the running app — confirmed via a full-codebase grep, the only call site is a standalone `smoke_test.py` script. Wire `start_browser()` into `main.py`'s `lifespan` (alongside the existing Finnhub client startup) and `close_browser()` into its shutdown path, mirroring `smoke_test.py`'s already-correct usage pattern.

### Why (context)

Surfaced debugging `#10.2`'s add-item flow — `PatchrightScraper._context` is always `None` in the running app, so any code path needing it (`detect_scraper_type`'s fallback probe, `AmazonCAScraper`'s actual scraping, `RetailerRouter`'s generic-hierarchy-failed fallback) instantly returns `status="error"` instead of actually trying. Broader than `#10.2` — this affects the **scheduled price-scraper job** (`jobs.py`'s `poll_prices` → `_process_item`, every 6h) for every existing/future `amazon.ca` listing and any listing whose `scraper_type` resolved to `"patchright"`, not just newly-added items. Confirmed live: manually starting the browser (`PatchrightScraper.start_browser()`) and calling `AmazonCAScraper().get_price(...)` against a real Amazon product page correctly returned a real price — the scraper code itself works, it's purely a missing startup wire-up.

### Acceptance criteria

- [ ] `PatchrightScraper.start_browser()` called during `main.py`'s `lifespan` startup, before the app starts accepting requests
- [ ] `PatchrightScraper.close_browser()` called during `lifespan` shutdown
- [ ] A real `amazon.ca` listing's scheduled scrape (`poll_prices` / manual `POST /api/poll/prices` trigger) successfully returns a real price, not `last_scrape_status: "error"`
- [ ] `detect_scraper_type`'s Patchright fallback (for unknown domains that fail `HTTPScraper`) actually attempts a real headless-browser probe instead of instant-failing
- [ ] App startup time impact is acceptable — launching a persistent browser context adds real startup latency; confirm it doesn't meaningfully delay the app becoming ready

---

## [ ] Issue #41 — Immediate First Scrape on Item/Listing Add

**Type:** feat / AFK
**Estimate:** ~2h
**Blocked by:** #40 (Patchright must actually be running for this to do anything)

### What to build

Today, a newly-added product/listing shows `—` for price/status until the next scheduled 6h `poll_prices` cycle, or a manual `POST /api/poll/prices` call — nothing scrapes it at add-time. Add a background first-scrape: after `create_item`/`create_listing` returns its response (not blocking the request itself), fire a background task per newly-created listing that runs the same scrape logic `_process_item` (`jobs.py`) already does — write `PriceHistory`, update `Listing.last_price`/`last_scrape_status`, and (unconditionally, matching `_process_item`'s existing behavior) broadcast via the SSE mechanism `#36` already built.

**Deliberately not synchronous** — blocking the add request on a real scrape (up to ~30s for a `Patchright`-dependent site) would make "Saving…" hang unacceptably long for what's otherwise a fast bulk-create. Firing it after the response returns, and letting `#36`'s existing SSE push (`mutate('/api/proxy/items')` on the frontend, already wired) deliver the result when it lands, needs zero new frontend plumbing — the table already updates itself on any SSE-pushed change.

Likely needs extracting `_process_item`'s scrape-one-listing logic (currently coupled to iterating `poll_prices`'s active-listings query) into a reusable function callable both from the scheduler loop and from this new add-time trigger, rather than duplicating the scrape+write+broadcast logic in a second place.

### Why (context)

Surfaced testing `#10.2`'s add flow — adding a real `amazon.ca` listing correctly skips the add-time *probe* (by design, `RETAILER_MAP` fast path, unrelated to this), but that also means nothing ever fetches an actual price until the next 6h cycle. Reasonable expectation for anyone adding an item to want to see today's price and status immediately, not a multi-hour blank state.

### Acceptance criteria

- [ ] Adding a real, scrapable listing triggers a background scrape that completes within a reasonable time after the add response returns (not blocking `POST /api/items`/`POST .../listings` itself)
- [ ] That scrape writes `PriceHistory`, updates `last_price`/`last_scrape_status`, exactly like a normal scheduled cycle would
- [ ] The result reaches the frontend via `#36`'s existing SSE broadcast — no new frontend code needed, table updates itself same as any other push
- [ ] An alert-crossing first scrape (price already below target on add) still triggers Pushover/email via the existing `Event`/queue path, same as any other scrape
- [ ] A failed first scrape (bad URL, site down) sets `last_scrape_status: "error"` and doesn't block or fail the add itself — the item/listing stays created either way
- [ ] Bulk add with multiple URLs: each successful listing gets its own background first-scrape, not just the first one
