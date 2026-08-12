# Issue #3: Implementation

## Steps

### 1. `ScraperResult` (`result.py`)
- [x] Define `ScraperResult` dataclass: `price: float | None`, `status: Literal["ok", "oos", "error"]`

### 2. Config dicts (`config.py`)
- [x] `NEXTDATA_PATHS`: `{}` — empty override dict; add entries when heuristic picks wrong value in practice
- [x] `NEXTDATA_PATHS` only — `RETAILER_MAP` lives in `router.py` to avoid circular import (`config.py` would import `AmazonCAScraper`)

### 3. Base class + extraction methods (`base.py`)
- [x] `BaseScraper(ABC)` with `@abstractmethod async def get_price(url: str) -> ScraperResult`
- [x] `USER_AGENTS: list[str]` pool (5–10 current Chrome UA strings)
- [x] `_build_headers(ua: str) -> dict` — `Accept`, `Accept-Language: en-CA,en;q=0.9`, `Accept-Encoding`
- [x] `_parse_price(raw: str) -> float | None` — strip `$`, `CAD`, `,` thousand separators; handle both `,` and `.` decimal; return `float` or `None`
- [x] `_extract_shopify(html: str, url: str) -> ScraperResult | None`:
  - Parse `handle` from URL path (last segment, strip `.html`)
  - `GET {scheme}://{host}/products/{handle}.json` via httpx
  - If `?variant=` in URL, find matching variant; else use `variants[0]`
  - Check `variant["available"]` → `ScraperResult(price=None, status="oos")` if false
  - Return `ScraperResult(price=float(variant["price"]), status="ok")`
  - Return `None` if endpoint 404s or lacks `product` key (not a Shopify store)
- [x] `_extract_jsonld(html: str) -> ScraperResult | None`:
  - Find all `<script type="application/ld+json">` tags; parse each
  - Find object with `@type == "Product"` (or containing `offers`)
  - Extract `offers.price`; check `offers.availability` for `OutOfStock`
  - Return `ScraperResult` or `None` if not found
- [x] `_extract_og_price(html: str) -> ScraperResult | None`:
  - Find `<meta property="og:price:amount" content="...">` via BS4
  - Return `ScraperResult(price=_parse_price(content), status="ok")` or `None`
- [x] `_extract_nextdata(html: str, url: str) -> ScraperResult | None`:
  - Find `<script id="__NEXT_DATA__">`, parse JSON
  - If URL hostname in `NEXTDATA_PATHS`: use explicit path list via `reduce(operator.getitem, path, data)`; falls back to heuristic on KeyError
  - Else: recursive search for key named `"price"` with numeric float value (first match wins)
  - Return `ScraperResult` or `None`
- [x] `_run_hierarchy(html: str, url: str) -> ScraperResult`:
  - Call `_extract_shopify` → `_extract_jsonld` → `_extract_og_price` → `_extract_nextdata` in order
  - Return first non-None result
  - Return `ScraperResult(price=None, status="error")` if all return `None`

### 4. `HTTPScraper` (`http_scraper.py`)
- [x] `get_price(url)`: httpx AsyncClient GET with random UA + `_build_headers`; 10s timeout
- [x] Pass response HTML to `_run_hierarchy(html, url)`
- [x] Wrap in `try/except Exception` → `return ScraperResult(price=None, status="error")`

### 5. `PatchrightScraper` + `AmazonCAScraper` (`patchright_scraper.py`)
- [x] `PatchrightScraper(BaseScraper)`:
  - Class-level `_browser: Browser | None = None`
  - `async def start_browser()` — `patchright.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH"))`; falls back to auto-detect locally
  - `async def close_browser()` — closes `_browser` and `_playwright`, sets both to `None`
  - `get_price(url)`: open new page, `page.goto(url, wait_until="domcontentloaded")`, get `page.content()`, pass to `_run_hierarchy(html, url)`
  - Wrap in `try/except Exception` → `return ScraperResult(price=None, status="error")`
- [x] `AmazonCAScraper(PatchrightScraper)`:
  - `_PRICE_SELECTOR = "#corePriceDisplay_desktop_feature_div .a-offscreen"` (single element, full price string — avoids whole+fraction concat bug)
  - `MAX_RETRIES = 2`
  - `get_price(url)`: open page; locate selector; `_parse_price()` on text content; return `ScraperResult(price=float, status="ok")`
  - Retry up to `MAX_RETRIES` on `None` result; return `ScraperResult(price=None, status="error")` after exhausting

### 6. `RetailerRouter` (`router.py`)
- [x] `RETAILER_MAP = {"amazon.ca": AmazonCAScraper}` defined here (not `config.py`)
- [x] `async def get_price(url: str, scraper_type: str | None = None) -> ScraperResult`:
  - Extract hostname; strip `www.`
  - If hostname in `RETAILER_MAP`: instantiate explicit scraper → call `get_price(url)` (ignores `scraper_type`)
  - If `scraper_type == "patchright"`: skip HTTPScraper, go straight to `PatchrightScraper().get_price(url)`
  - Else: `result = await HTTPScraper().get_price(url)`; if `result.status == "error"` → fallback to `PatchrightScraper().get_price(url)`
  - Return final result

### 7. Migration (`0003_watch_item_scraper_type.py`)
- [x] Alembic migration: `ALTER TABLE watch_items ADD COLUMN scraper_type VARCHAR NULL`
- [x] Update `WatchItem` model: `scraper_type: Mapped[str | None] = mapped_column(String, nullable=True)`
- [x] `alembic upgrade head` applied

### 8. `__init__.py` exports
- [x] Re-export: `ScraperResult`, `BaseScraper`, `HTTPScraper`, `PatchrightScraper`, `AmazonCAScraper`, `RetailerRouter`
- [x] Re-export config: `NEXTDATA_PATHS`, `RETAILER_MAP`

### 9. Dockerfile wiring
- [x] In `backend/Dockerfile`: add shell glob to resolve Chromium path at build time:
  ```dockerfile
  RUN CHROMIUM_PATH=$(find /ms-playwright -name "chrome" -type f | head -1) && \
      echo "CHROMIUM_PATH=$CHROMIUM_PATH" >> /etc/environment
  ```

### 10. Validation
- [x] `_parse_price`: 14 table-driven unit tests — all passing
- [x] Unit tests: 50/50 passing (`tests/scraper/test_base.py`, `tests/scraper/test_router.py`)
- [x] `ScraperResult(status="error")` on connection error — unit tested
- [x] `alembic upgrade head` applies migration cleanly
- [x] Live smoke: `HTTPScraper` against deadstock.ca (Shopify ✓), BestBuy.ca (headful ✓), SSENSE (headful ✓)
- [x] Live smoke: `AmazonCAScraper` against amazon.ca/gp/aw/d/B0GSS4SGZR/ — headful ✓ via `[data-pricetopay-label]`
- [ ] Verify `ScraperResult(status="oos")` on a known OOS Shopify item (deferred — not blocking)
