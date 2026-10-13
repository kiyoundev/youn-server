# Issue #60: Amazon Scraper — New vs Used Pricing

## PR / Branch
- **Branch:** `feature/60-amazon-new-vs-used-price`
- **PR Title:** `main | feature - 60 - Amazon new vs used price`
- **Note:** this repo commits straight to `main` (solo project); branch/PR fields are nominal.

## Scope
Part 1 (false-drop guarantee) and part 1b (used-price info icon) only. Part 2 (a used-condition listing with `Listing.condition`, UI label) is deferred to a new issue.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ⬜ Not started | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] A used-only or no-featured-offer page reports `oos`, never a price (re-verified against real amazon.ca HTML)
- [ ] The new price is read only from inside the new buy box; if it can't be found the scrape is an `error` with a specific reason, never the page-wide fallback
- [ ] A both-offers page reports the new price, not the used one
- [ ] `Listing.used_price` (nullable) is set from `#usedBuySection .offer-price` on a used-only `oos` result and cleared on the next `ok`
- [ ] The retailer row shows an info icon with the used price only when the listing is `oos` and `used_price` is not null
- [ ] Used price never touches `PriceHistory`, the chart, or alerts
- [ ] Fixtures (trimmed, no tokens/postal code): new only (plain), used only, no featured offer, both offers (accordion)
- [ ] New price is found by walking up from `#add-to-cart-button`; the used row and the "Other sellers" box are never read
- [ ] Migration applied locally and on the Pi
- [ ] `.doc/issues.md` #60 criteria rewritten; deferred part 2 moved to a new issue

## Estimated Effort
- Pi HTML capture and selector check: **0.5 hours**
- Parsers, scraper wiring, tests: **2 hours**
- Migration, `process_item`, API, icon: **1.5 hours**
- Live verification: **0.5 hours**
- **Total: ~4.5 hours**
