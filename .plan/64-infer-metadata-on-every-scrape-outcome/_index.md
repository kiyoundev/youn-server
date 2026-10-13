# Issue #64: Infer Item Name, Currency and Retailer on Every Scrape Outcome

## PR / Branch
- **Branch:** `fix/64-infer-metadata-on-every-scrape-outcome`
- **PR Title:** `main | fix - 64 - Infer metadata on every scrape outcome`
- **Note:** this repo commits straight to `main` (solo project); branch/PR fields are nominal.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | 🟨 Code + tests done; live checks pending | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] An `"oos"` scrape that returns title, currency and site name fills `Product.name`, `Product.currency`, `Listing.retailer` under the same guards as `ok`
- [ ] An `"error"` scrape that returns metadata applies it the same way
- [ ] `ok` behaviour unchanged, including the locked Product read for alert dedup (#48)
- [ ] `AmazonCAScraper` returns title and currency on `ok`, `oos` and the "price not found in the new buy box" error (from the parsed soup, no Playwright call); nothing for a redirected variant or captcha page
- [ ] IKEA and Uniqlo attach every metadata field they parse on all outcomes that got far enough to parse
- [ ] Generic path (`_run_hierarchy`): name and retailer only on `ok`/`oos`; currency still attached on errors; bot-block pages carry no metadata at all
- [ ] Existing "Untitled" product with an `"oos"` listing gets its name on the next scrape
- [ ] Tests: `process_item` per branch, per-scraper per status, block-page / 404-page test
- [ ] Live-verified: `B0GSS5TK8R` gets "Apple AirPods Max 2 - Purple", currency CAD, stays `"oos"`

## Estimated Effort
- Implementation: **2 hours**
- Testing: **1 hour**
- **Total: 3 hours**
