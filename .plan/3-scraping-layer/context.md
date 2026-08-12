# Issue #3: Context

## Issue Description

Build the complete scraping layer: abstract base class, two concrete scraper implementations, shared universal extraction methods, a typed result, and a domain router. Any product URL is supported without site-specific config — extraction hierarchy tries standardized methods in order.

## Component Summary

### Current State

`backend/app/services/scraper/__init__.py` exists but is empty (1 line). No scraper classes, no config dicts, no router. The `services/` and `services/scraper/` directories are in place.

All dependencies already in `requirements.txt`: `httpx[http2]`, `beautifulsoup4`, `patchright`.

### Target State

`backend/app/services/scraper/` becomes a full package:

```
backend/app/services/scraper/
├── __init__.py          # re-exports all public symbols
├── result.py            # ScraperResult dataclass
├── config.py            # SELECTORS (amazon_ca only), NEXTDATA_PATHS (override dict), RETAILER_MAP
├── base.py              # BaseScraper ABC + shared extraction methods + _parse_price
├── http_scraper.py      # HTTPScraper
├── patchright_scraper.py# PatchrightScraper + AmazonCAScraper
└── router.py            # RetailerRouter
```

New Alembic migration: `backend/alembic/versions/0003_watch_item_scraper_type.py`

### Extraction Hierarchy

Tried in order by both `HTTPScraper` (on httpx-fetched HTML) and `PatchrightScraper` (on rendered DOM):

| Step | Method | Signal used | OOS detection |
|------|--------|-------------|---------------|
| 1 | `_extract_shopify()` | `/products/{handle}.json` | `variants[*].available` |
| 2 | `_extract_jsonld()` | `<script type="application/ld+json">` → `offers.price` | `offers.availability` |
| 3 | `_extract_og_price()` | `<meta property="og:price:amount">` | None |
| 4 | `_extract_nextdata()` | `__NEXT_DATA__` heuristic; `NEXTDATA_PATHS` override | None |

First method that returns a result wins. Amazon skips the hierarchy — uses explicit CSS selector.

### `ScraperResult`

```python
@dataclass
class ScraperResult:
    price: float | None
    status: Literal["ok", "oos", "error"]
```

Caller (Issue #6) distinguishes OOS (`status="oos"`, log info) from error (`status="error"`, log warning). Both skip `PriceHistory` write.

## Impact & Risk

### Files Changed

- **`backend/app/services/scraper/__init__.py`** — add public re-exports
- **`backend/app/services/scraper/result.py`** — new; `ScraperResult` dataclass
- **`backend/app/services/scraper/config.py`** — new; `NEXTDATA_PATHS`, `RETAILER_MAP`
- **`backend/app/services/scraper/base.py`** — new; `BaseScraper` ABC + extraction methods + `_parse_price`
- **`backend/app/services/scraper/http_scraper.py`** — new; `HTTPScraper`
- **`backend/app/services/scraper/patchright_scraper.py`** — new; `PatchrightScraper`, `AmazonCAScraper`
- **`backend/app/services/scraper/router.py`** — new; `RetailerRouter`
- **`backend/alembic/versions/0003_watch_item_scraper_type.py`** — new; adds `scraper_type` nullable column to `watch_items`
- **`backend/app/models/watch_item.py`** — add `scraper_type: Mapped[str | None]`

### Dependencies

- **`PriceHistory` model** — caller (Issue #6) writes rows only on `status="ok"`; scraper never touches DB
- **`WatchItem.scraper_type`** — new nullable column; `None` = auto-detect at poll time; Issue #8 sets it at add-time via extraction probe

### Config Dict Design Notes

`NEXTDATA_PATHS` is an override dict, empty by default:
```python
NEXTDATA_PATHS: dict[str, list[str]] = {}
# Add only when heuristic picks wrong value:
# "ssense": ["props", "pageProps", "product", "price"]
```

`RETAILER_MAP` has one entry — only Amazon needs explicit routing:
```python
RETAILER_MAP = {
    "amazon.ca": AmazonCAScraper,
}
```

Amazon CSS selectors live on `AmazonCAScraper` as class constants — no `SELECTORS` dict needed:
```python
class AmazonCAScraper(PatchrightScraper):
    _WHOLE_SELECTOR = "#corePriceDisplay_desktop_feature_div .a-price-whole"
    _FRACTION_SELECTOR = "#corePriceDisplay_desktop_feature_div .a-price-fraction"
```
Price is whole + fraction concatenated before `_parse_price()`.
