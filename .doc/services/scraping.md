# Scraping

## Page Type Categories

| Category | Description | Approach |
|----------|-------------|----------|
| Plain SSR | Price in initial HTML response | `HTTPScraper` → `_run_hierarchy()` |
| Next.js `__NEXT_DATA__` | Price in embedded JSON script tag | `HTTPScraper` → `_extract_nextdata()` |
| Shopify | Built-in JSON product API | `HTTPScraper` → `_extract_shopify()` |
| JS-rendered + bot detection | Price client-side + bot blocking | `PatchrightScraper` (headless Chromium) |

## Design

Abstract base class with two concrete scraper implementations. `HTTPScraper` handles all sites that return price in the initial HTML response via an extraction hierarchy. `PatchrightScraper` handles JS-rendered and bot-blocked sites. A `RetailerRouter` maps known domains to the correct scraper — adding a new retailer is a config change, not a code change.

```
BaseScraper (ABC)
├── HTTPScraper        — httpx; tries extraction hierarchy: Shopify → JSON-LD → OG → __NEXT_DATA__
└── PatchrightScraper  — headless Chromium via patchright; JS-rendered + bot-blocked
    └── AmazonCAScraper  — Amazon-specific selectors + patchright CDP patches
```

## Retailer Routing

```python
RETAILER_MAP = {
    "amazon.ca": AmazonCAScraper,
    # known domains that need explicit scraper assignment
    # unknown domain → HTTPScraper with fallback to PatchrightScraper
}
```

For unknown domains, `RetailerRouter` tries `HTTPScraper` first. If that returns `"error"`, it falls back to `PatchrightScraper`. The result is cached as `scraper_type` on `WatchItem` (`null` = HTTP works, `"patchright"` = needs headless browser) so poll cycles skip the failed path.

## Selector / Path Config

`NEXTDATA_PATHS` in `scraper/config.py` stores explicit JSON paths for sites where the heuristic `_search_price_recursive()` picks the wrong value:

```python
NEXTDATA_PATHS = {
    # "ssense.com": ["props", "pageProps", "product", "price"],
}
```

## Amazon.ca Strategy

Amazon aggressively fingerprints headless browsers at the CDP (Chrome DevTools Protocol) level. Mitigation layers:

1. **patchright** — patches CDP responses to remove automation signals at the protocol level; more effective than stealth plugins which work at the JS layer
2. **Realistic headers** — User-Agent matching a current Chrome version, `Accept-Language: en-CA`
3. **Fallback** — if `PatchrightScraper` returns `None` after 2 retries, skip the poll cycle and log a warning; do not crash the scheduler

## Scraper Behaviour

- `get_price(url) -> float | None` — returns `None` on any failure
- Caller (scheduler job) logs a warning on `None`; skips `PriceHistory` write for that cycle
- Patchright browser instance is shared across requests within a job run, closed after job completes
- HTTP requests use a rotating User-Agent from a small pool

## ARM64 / Pi Consideration

Use `mcr.microsoft.com/playwright/python:v1.x.x-jammy` as base Docker image — bundles a verified ARM64 Chromium. Patchright is installed on top via `pip install patchright` and uses this existing Chromium binary via `executable_path` or `patchright install chromium` (which reuses cached binaries). No separate Chromium install needed.
