# Issue #44: Infer Retailer Display Name & Item Name from Scrape Metadata

## PR / Branch
- **Branch:** `feature/44-infer-retailer-item-name`
- **PR Title:** `main | feature - 44 - Infer retailer/item name from scrape metadata`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done (code + unit tests; manual verification left to you) | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
<!-- Derived from the issue's own AC, refined during grilling -->
- [x] Adding an item without a name gets a sensible inferred `Product.name` once the first scrape completes, without blocking creation — code done, unit-tested; **live check still needed (you)**
- [x] Retailer badge shows a human-readable name (e.g. "Muddy George") instead of the raw hostname-derived fallback, for domains not already in `RETAILER_DISPLAY_NAMES` — code done, unit-tested; **live check still needed (you)**
- [x] A user-provided `Product.name` or a manually-edited `Listing.retailer` is never overwritten by inference (guard: retailer only overwritten while it still equals the deterministic hostname fallback; product.name only filled while still `NULL`) — unit-tested (both guard directions)
- [x] Inference failure (no extractable title/site name) degrades gracefully — never blocks creation or scraping, `Product.name` simply stays `NULL` / `Listing.retailer` stays the hostname fallback — confirmed by the full suite staying green untouched wherever `ScraperResult` mocks don't set the new fields
- [x] `RETAILER_MAP`-mapped retailers (`amazon.ca` → `"Amazon"`) unaffected for the retailer badge — static override still takes priority; Amazon listings still get `product_title` inference for `Product.name` via a dedicated extraction in `AmazonCAScraper`
- [x] Bulk-add failure toast shows each failed URL's hostname-derived retailer name, not the raw URL — unit-tested across all 5 failure paths; **live check still needed (you)**
- [x] Existing single-name/single-retailer products (the common case, name always provided) are unaffected — no behavior change when nothing needs inferring — confirmed, full pre-existing suite stayed green throughout

## Estimated Effort
- Implementation: **3.5 hours** (matches issue estimate) — done
- Testing: **1 hour** — unit tests done; manual live verification still on you
- **Total: 4.5 hours** — code complete, 4 manual checks remaining
