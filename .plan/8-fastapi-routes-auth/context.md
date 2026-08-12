# Issue #8: Context

## Issue Description

Build all API routes, shared API key auth, CORS, and rate limiting on manual poll triggers. Original scope (`.doc/issues.md#L541-578`):

- `core/auth.py` — `verify_api_key` dependency, applied at router-mount time, `GET /api/health` exempt
- `api/items.py` — GET/POST/PATCH/DELETE `/api/items`, GET `/api/items/{id}/history`
- `api/stocks.py` — GET/POST/PATCH/DELETE `/api/stocks`
- `api/poll.py` — POST `/api/poll/prices`, POST `/api/poll/stocks`, rate-limited to 1 call / 5 min
- `api/health.py` — GET `/api/health`

Before implementation, the issue was checked against `.doc/api.md` for alignment. Several conflicts and gaps surfaced and were resolved through discussion — both docs were updated to match the final design. See [schema.md](schema.md) for the resulting API contract and [challenges.md](challenges.md) for the riskier parts of this expanded scope.

## Component / Route Summary

### Current State

- `app/main.py` has two inline stub routes: `GET /api/health` and `POST /api/poll/prices` (no auth, no rate limit, no concurrency guard — explicitly called out as a TODO in a code comment).
- No `app/api/` routers exist yet (`app/api/__init__.py` is empty).
- No `app/core/auth.py` exists.
- `app/schemas/watch_item.py` and `app/schemas/stock_alert.py` only have `*Response` schemas — no `Create`/`Update` request schemas.
- `WatchItem.scraper_type` column already exists (added in migration `0003`), but nothing writes to it yet.
- `RetailerRouter.get_price(url, scraper_type)` already implements the HTTP→Patchright fallback; it just isn't driven by any API route yet.
- `FinnhubClient` (in `app/services/stocks.py`) already has `add_alert()`, `remove_alert()`, `update_alert()`, `get_price()`, `validate_ticker()`, `_check_threshold()` — all built for Issue #4, unused by any route yet.
- `scheduler/jobs.py` has `poll_prices()` only — no `poll_stocks()` job exists.
- `consumers/analysis.py` (Issue #7) creates a `pending` `AnalysisResult` automatically when a stock threshold fires and `run_analysis=True` — it's a stub; no real TradingAgents integration yet. This issue's `/analyze` route reuses the same "create pending row" pattern for the manual-trigger path; the real analysis pipeline stays out of scope.
- `tests/api/test_poll_routes.py` imports `trigger_poll` directly from `app.main` — will break once the poll route moves into `app/api/poll.py`.

### Target State

All routes live in `app/api/{items,stocks,poll,health}.py`, mounted in `main.py` with `dependencies=[Depends(verify_api_key)]` (except health). `app/main.py` loses its two inline routes entirely. New Pydantic request schemas (`WatchItemCreate`, `WatchItemUpdate`, `StockAlertCreate`, `StockAlertUpdate`) are added. Two new DB unique constraints are added via Alembic migration. A new `poll_stocks()` job is added alongside `poll_prices()`, both protected by an in-memory `asyncio.Lock` shared between the manual-trigger route and the APScheduler-scheduled job.

## Key Decisions From `api.md` Alignment Review

These were resolved through discussion before implementation — recorded here so the "why" isn't lost:

1. **Auth bug fix**: `api.md`'s original auth snippet used `Header(...)` (required), which makes FastAPI return 422 on a missing header — contradicting the acceptance criterion that requires 401. Fixed to `Header(None)` + manual check.
2. **Domain handling**: `api.md` originally said "400 if domain unsupported." This contradicted both `RetailerRouter`'s actual design (accepts any domain, falls back HTTP→Patchright) and the acceptance criteria (Shopify URLs must succeed). Resolved: accept all domains; 400 only if *both* scraping methods fail on probe.
3. **`scraper_type` exposed in response** — added to `WatchItemResponse`/`WatchItem` TS interface (was previously response-shape-incomplete).
4. **Poll response shape**: `api.md` wanted `{ triggered: true, items_checked: int }`, but `items_checked` is unknowable at response time since polling runs in a `BackgroundTask` *after* the response is sent. Resolved to `{"status": "queued"}` — honest about what actually happened (task queued, not run).
5. **`validate_ticker` scope**: confirmed Finnhub REST is the sole validation source; yfinance is scoped to historical chart data only, never live validation. `api.md`'s "yfinance/Finnhub, 400 if both fail" wording was stale.
6. **Concurrency guard added** (not in original issue scope): manual poll triggers had no lock against overlapping with the scheduled job or each other — this was an existing TODO comment in `main.py`. Added `asyncio.Lock` around both `poll_prices()` and a new `poll_stocks()`.
7. **`poll_stocks()` didn't exist** — `/api/poll/stocks` had nothing to call. Designed as a manual REST fallback alongside the always-on Finnhub WebSocket: re-checks all actively-cached tickers via `FinnhubClient.get_price()` + reuses `_check_threshold()`, covering any price movement missed during a brief WS disconnect.
8. **`/api/stocks/{id}/analyze` + `/api/stocks/{id}/analysis`** — present in `api.md` but absent from the issue's router list. Added to scope; `/analyze` only creates a pending `AnalysisResult` row (real TradingAgents analysis is still a future stub).
9. **Singular GET endpoints added**: `GET /api/items/{id}` and `GET /api/stocks/{id}` were missing — only list + sub-resource routes existed. Added for REST completeness (PATCH/DELETE/sub-routes already assumed a known ID; these read it directly without listing everything).
10. **404 handling, 422 validation on `scraper_type`, 204 on DELETE** — none of these were explicitly specified; added as standard REST defaults.
11. **Duplicate prevention added** (not in original issue scope): `UNIQUE(url)` on `WatchItem`, `UNIQUE(ticker, direction)` on `StockAlert` — enforced across all rows regardless of `active` state. Returns 409 on conflict. Frontend will do an optimistic client-side check against its already-loaded list; the DB constraint is the authoritative guard.

## Impact & Risk

### Files Changed
- **`app/core/auth.py`** (new) — `verify_api_key` dependency
- **`app/api/items.py`** (new) — items router
- **`app/api/stocks.py`** (new) — stocks router
- **`app/api/poll.py`** (new) — poll trigger router
- **`app/api/health.py`** (new) — health router
- **`app/main.py`** — remove inline routes, mount new routers, add CORS middleware
- **`app/schemas/watch_item.py`** — add `WatchItemCreate`, `WatchItemUpdate`; add `scraper_type` to `WatchItemResponse`
- **`app/schemas/stock_alert.py`** — add `StockAlertCreate`, `StockAlertUpdate`
- **`app/services/scraper/router.py`** — add scraper-type detection helper for POST-time probing
- **`app/scheduler/jobs.py`** — add `poll_stocks()`, add `asyncio.Lock` guards to both jobs
- **`app/models/watch_item.py`** — add `unique=True` on `url`
- **`app/models/stock_alert.py`** — add composite unique constraint on `(ticker, direction)`
- **`alembic/versions/0004_*.py`** (new) — migration for the two unique constraints
- **`tests/api/test_poll_routes.py`** — rewrite to import from `app.api.poll` instead of `app.main`

### Dependencies
- **`FinnhubClient`** (`app.state.finnhub`) — stocks router must call `add_alert()`/`remove_alert()`/`update_alert()` on create/update/delete to keep the live WS subscription cache in sync; `poll_stocks()` reuses `get_price()` + `_check_threshold()`
- **`RetailerRouter`** — items router's POST handler uses it (or a thin wrapper) to probe unknown domains

### Breaking Changes
- `tests/api/test_poll_routes.py` currently imports `trigger_poll` from `app.main` — this import path will no longer exist once the route moves. Must be rewritten as part of this issue, not left broken.
