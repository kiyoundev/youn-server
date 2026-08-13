# Issue #8: Implementation

## Steps

### 1. Auth & App Wiring
- [x] `app/core/auth.py` — `verify_api_key` dependency (`Header(None)`, manual 401 check)
- [x] `app/main.py` — add `CORSMiddleware` reading `settings.cors_origins.split(",")`
- [x] `app/api/health.py` — `GET /api/health` router (no auth), mounted in `main.py`, inline stub removed
- [x] `app/main.py` — removed inline `POST /api/poll/prices` stub route (done in step 6)
- [x] `app/main.py` — mounted `items`, `stocks`, `poll` routers with `dependencies=[Depends(verify_api_key)]` (done in step 6)

### 2. Schemas
- [x] `app/schemas/watch_item.py` — add `WatchItemCreate`, `WatchItemUpdate` (no changes to `WatchItemResponse` — `scraper_type` stays write-only, not exposed)
- [x] `app/schemas/stock_alert.py` — add `StockAlertCreate`, `StockAlertUpdate`
- [x] `app/schemas/analysis_result.py` — change `AnalysisResultResponse.triggered_price` from `float` to `float | None`

### 3. Database Migration
- [x] `app/models/watch_item.py` — `url` column → `unique=True`
- [x] `app/models/stock_alert.py` — add `UniqueConstraint("ticker", "direction")` to `__table_args__`
- [x] `app/models/analysis_result.py` — `triggered_price` column → `nullable=True`
- [x] Checked dev DB for duplicates — `watch_items`/`stock_alerts` were empty, nothing to dedupe
- [x] Generated + applied Alembic migration `0004_unique_constraints_nullable_triggered_price.py` — verified constraints landed via `pg_constraint`, verified downgrade/upgrade cycle works cleanly

### 4. Scraper Probe Helper
- [x] `app/services/scraper/router.py` — added `detect_scraper_type(url)` module-level function, exactly as planned. Raises `ValueError` if both scrapers fail.
- [x] Added 4 unit tests in `tests/scraper/test_router.py` (HTTP ok/oos → `None`, HTTP error → Patchright success → `"patchright"`, both fail → raises)
- [x] Items router catches the `ValueError` and converts to 400 (done in step 6)

### 5. Concurrency Lock + New Job
- [x] `app/scheduler/jobs.py` — added module-level `_prices_lock = asyncio.Lock()`; `poll_prices()` skips (logs warning) if already locked
- [x] `app/services/stocks.py` — added `FinnhubClient.cached_tickers()` and `check_threshold()` public methods
- [x] `app/scheduler/jobs.py` — added `poll_stocks(finnhub)` with its own `_stocks_lock`, using the new public methods (no private-internal access)
- [x] Added 5 new tests in `tests/scheduler/test_jobs.py` (lock-skip for both jobs, `poll_stocks` happy path, `None`-price skip, per-ticker error isolation) + 2 in `tests/test_stocks.py` for the new `FinnhubClient` methods
- [x] Both `app.main`'s lifespan-scheduled job (`poll_prices`, every 6h) and the future manual-trigger route share the same lock since they call the same function (module-level lock, not per-call)

### 6. Routers
- [x] `app/api/health.py` — `GET /api/health` → `{"status": "ok"}` (done in step 1)
- [x] `app/api/items.py` — all 6 routes implemented exactly as planned (list, get-by-id, create with probe/override/RETAILER_MAP logic, update, delete, history)
- [x] `app/api/stockalerts.py` — all 7 routes implemented exactly as planned, including `FinnhubClient` cache sync on create/update/delete and debug-only `/analyze`
- [x] `app/api/poll.py` — both routes implemented with independent rate-limit state
- [x] `app/main.py` — mounted `items`, `stocks`, `poll` with `dependencies=[Depends(verify_api_key)]`; removed old inline poll stub entirely
- [x] Verified all 19 routes registered correctly (`/api/health` + 6 items + 7 stocks + 2 poll + FastAPI's own docs routes)

### 7. Testing & Validation
- [x] Rewrote `tests/api/test_poll_routes.py` to import from `app.api.poll` instead of `app.main` (6 tests, incl. independent rate-limit windows)
- [x] Unit test: missing/wrong `X-API-Key` → 401 across `items`/`stocks`/`poll` routers (`tests/test_auth_and_cors.py`)
- [x] Unit test: `GET /api/health` → 200 with no header
- [x] Unit test: `POST /api/items` with known-domain (`RETAILER_MAP`) URL → probe skipped, `retailer` derived from hostname (`tests/api/test_items_routes.py`)
- [x] Unit test: `POST /api/items` unknown domain → `detect_scraper_type` awaited, result stored
- [x] Unit test: `POST /api/items` with explicit `scraper_type = "patchright"` → stored as-is, probe skipped
- [x] Invalid `scraper_type` value → 422 handled automatically by Pydantic `Literal` validation (verified in step 2)
- [x] Unit test: `POST /api/items` duplicate `url` → 409 via `IntegrityError` catch
- [x] Unit test: `POST /api/stockalerts` with invalid ticker (mocked `validate_ticker` → `False`) → 400
- [x] Unit test: `POST /api/stockalerts` duplicate `(ticker, direction)` → 409
- [x] Unit test: `POST /api/poll/prices` / `/api/poll/stocks` called twice within 5 min → second call 429 (independent windows verified)
- [x] Unit test: `poll_prices()` / `poll_stocks()` skip if lock already held (step 5)
- [x] Real-DB verification: `DELETE /api/items/{id}` cascades `PriceHistory` rows (2 rows written, both gone after delete)
- [x] Unit test: CORS preflight allows configured origin (`tests/test_auth_and_cors.py`)
- [x] Unit test: `POST /api/stockalerts/{id}/analyze` — 409 if pending `AnalysisResult` exists for ticker; also covered null-`last_price` case
- [x] Real-DB smoke test: create → get → duplicate 409 → delete → 404, full round trip against dev Postgres, verified clean afterward

**Final count: 158 tests passing** (up from 107 at branch start).

### 8. Cleanup
- [x] Stale "No auth yet... no concurrency guard" comment removed along with the whole inline stub it was attached to (step 6)
- [x] `app/api/__init__.py` confirmed empty is fine — matches existing pattern (`from app.consumers import dispatcher`); `main.py` does `from app.api import health, items, poll, stocks` with no re-exports needed
