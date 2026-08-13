# Issue #8: Schema & API Contract

Full contract is maintained in `.doc/api.md` (already updated to reflect every decision below). This file is the implementation-facing breakdown.

## Auth

```python
# app/core/auth.py
async def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    if x_api_key is None or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

Mounted via `dependencies=[Depends(verify_api_key)]` at `include_router()` time for `items`, `stocks`, `poll` routers. `health` router has no dependency.

## API Routes

### `GET /api/items`
- **Response:** `list[WatchItemResponse]` — bare array, no pagination wrapper

### `GET /api/items/{id}`
- **Response:** `WatchItemResponse`
- **Error cases:** 404 if not found

### `POST /api/items`
- **Request:** `WatchItemCreate` — `{ name, url, target_price, scraper_type? }`
- **Response:** `WatchItemResponse` (201)
- **Logic:**
  1. Derive `retailer` from URL hostname
  2. If hostname in `RETAILER_MAP` → `scraper_type = null`, skip probe
  3. Else if `scraper_type` provided in body → must be `null` or `"patchright"` (422 otherwise), skip probe
  4. Else probe: try `HTTPScraper().get_price(url)` → if status != `"error"`, `scraper_type = null`; else try `PatchrightScraper().get_price(url)` → if status != `"error"`, `scraper_type = "patchright"`; else 400
- **Error cases:** 422 malformed URL or invalid `scraper_type`, 400 if neither scraper works, 409 if `url` already exists (any `active` state)

### `PATCH /api/items/{id}`
- **Request:** `WatchItemUpdate` — `{ name?, target_price?, active? }`
- **Response:** `WatchItemResponse`
- **Error cases:** 404 if not found

### `DELETE /api/items/{id}`
- **Response:** 204 No Content
- **Error cases:** 404 if not found
- Cascades to `PriceHistory` (already enforced at DB + ORM level)

### `GET /api/items/{id}/history?days=30`
- **Response:** `list[PriceHistoryResponse]`
- **Error cases:** 404 if item not found

### `GET /api/stockalerts`
- **Response:** `list[StockAlertResponse]`

### `GET /api/stockalerts/{id}`
- **Response:** `StockAlertResponse`
- **Error cases:** 404 if not found

### `POST /api/stockalerts`
- **Request:** `StockAlertCreate` — `{ ticker, target_price, direction, run_analysis? }`
- **Response:** `StockAlertResponse` (201)
- **Logic:** validate via `FinnhubClient.validate_ticker()` (Finnhub REST only); on success, call `app.state.finnhub.add_alert(alert)` to sync the WS subscription cache
- **Error cases:** 400 if ticker invalid, 409 if `(ticker, direction)` already exists (any `active` state)

### `PATCH /api/stockalerts/{id}`
- **Request:** `StockAlertUpdate` — `{ target_price?, direction?, active?, run_analysis? }`
- **Response:** `StockAlertResponse`
- **Logic:** sync `app.state.finnhub` cache — `update_alert()` for field changes; if `active` flips to `false`, call `remove_alert()` (unsubscribe); if it flips to `true`, call `add_alert()` (resubscribe)
- **Error cases:** 404 if not found

### `DELETE /api/stockalerts/{id}`
- **Response:** 204 No Content
- **Logic:** call `app.state.finnhub.remove_alert(id, ticker)` to unsubscribe
- **Error cases:** 404 if not found

### `POST /api/stockalerts/{id}/analyze`
- **Debug/manual-trigger tool** — the real usage path is automatic (threshold crossing + `run_analysis=true`, handled by `consumers/analysis.py`). This route exists to force-run the pipeline without waiting for a real crossing.
- **Response:** `AnalysisResultResponse` (201)
- **Logic:**
  1. 404 if `stock_alert_id` not found
  2. 409 if an `AnalysisResult` with `status in ("pending", "running")` already exists for this `ticker`
  3. No live price fetch — use `alert.last_price` directly as `triggered_price` (may be `null` if this alert has never fired)
  4. Create `AnalysisResult(stock_alert_id, ticker, triggered_price=alert.last_price, status="pending")`, return it immediately

### `GET /api/stockalerts/{id}/analysis?limit=10`
- **Response:** `list[AnalysisResultResponse]`, ordered `created_at desc`
- **Error cases:** 404 if alert not found

### `POST /api/poll/prices`
- **Response:** `{"status": "queued"}` (200)
- **Error cases:** 429 if called within 5 min of the last call (in-memory timestamp)
- Queues `poll_prices()` as a `BackgroundTask`; guarded by a shared `asyncio.Lock` against the scheduled job

### `POST /api/poll/stocks`
- **Response:** `{"status": "queued"}` (200)
- **Error cases:** 429 if called within 5 min of the last call
- Queues `poll_stocks(app.state.finnhub)` as a `BackgroundTask`

### `GET /api/health`
- **Response:** `{"status": "ok"}` (200), no auth

## New Pydantic Schemas

```python
# app/schemas/watch_item.py
class WatchItemCreate(BaseModel):
    name: str
    url: str
    target_price: float
    scraper_type: Literal["patchright"] | None = None

class WatchItemUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None
    active: bool | None = None

class WatchItemResponse(BaseModel):
    id: int
    name: str
    url: str
    retailer: str
    target_price: float
    last_price: float | None
    alerted_at: datetime | None
    active: bool
    created_at: datetime
    model_config = {"from_attributes": True}
    # scraper_type intentionally omitted — write-only, used internally at poll time only
```

```python
# app/schemas/stock_alert.py
class StockAlertCreate(BaseModel):
    ticker: str
    target_price: float
    direction: Literal["above", "below"]
    run_analysis: bool = False

class StockAlertUpdate(BaseModel):
    target_price: float | None = None
    direction: Literal["above", "below"] | None = None
    active: bool | None = None
    run_analysis: bool | None = None
```

```python
# app/schemas/analysis_result.py — existing AnalysisResultResponse needs one change
triggered_price: float | None   # was: float (non-nullable) — see Database Changes below
```

## Database Changes

```python
# app/models/watch_item.py
url: Mapped[str] = mapped_column(String, unique=True)

# app/models/stock_alert.py
__table_args__ = (UniqueConstraint("ticker", "direction"),)

# app/models/analysis_result.py
triggered_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # was non-nullable
```

New Alembic migration `0004_unique_url_ticker_direction.py` — adds both unique constraints and relaxes `analysis_results.triggered_price` to nullable. **Note:** if any duplicate `url`/`(ticker, direction)` rows already exist in the dev DB, the unique constraints will fail to apply until they're manually deduplicated first (see [challenges.md](challenges.md)).
