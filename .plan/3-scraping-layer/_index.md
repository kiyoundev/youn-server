# Issue #3: Scraping Layer

## PR / Branch
- **Branch:** `feature/3-scraping-layer`
- **PR Title:** `main | feature - 3 - Scraping Layer`

## Task Status

| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ⬜ Not started | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria

- [ ] `RetailerRouter` routes `amazon.ca` → `AmazonCAScraper`; unknown domain → `HTTPScraper` with `PatchrightScraper` fallback on `status="error"`
- [ ] `AmazonCAScraper.get_price()` returns `ScraperResult(price=float, status="ok")` for a live Amazon.ca product URL
- [ ] `HTTPScraper.get_price()` extracts price via schema.org JSON-LD for a live BestBuy.ca product URL
- [ ] `HTTPScraper.get_price()` extracts price via Shopify API for a live deadstock.ca product URL
- [ ] `HTTPScraper.get_price()` extracts price via `__NEXT_DATA__` heuristic for a live SSENSE product URL
- [ ] `PatchrightScraper.get_price()` extracts price on a JS-rendered URL where `HTTPScraper` returns `status="error"`
- [ ] OOS item returns `ScraperResult(price=None, status="oos")` — distinct from error
- [ ] Any scraper returns `ScraperResult(price=None, status="error")` on connection error without raising
- [ ] `_parse_price("$1,299.99 CAD")` returns `1299.99`
- [ ] Patchright browser instance is shared within a job run and closed after
- [ ] New Alembic migration adds `watch_items.scraper_type` nullable column

## Estimated Effort
- Implementation: **5 hours**
- Testing: **1 hour**
- **Total: 6 hours**
