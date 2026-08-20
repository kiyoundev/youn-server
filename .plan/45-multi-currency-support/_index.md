# Issue #45: Multi-Currency Support (Detection, Display, FX-Converted Total)

## PR / Branch
- **Branch:** `feature/45-multi-currency-support`
- **PR Title:** `main | feature - 45 - Multi-currency support`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Scope Note
Two rounds of scope revision via grill-me (2026-08-19):
1. Currency is **product-level**, not per-`Listing` — one product never mixes currencies across
   its retailer listings. Removes `Listing.currency` and FX conversion for the alert/"cheapest"
   comparison entirely (stays native-currency, untouched).
2. FX conversion **re-added**, narrower: the watchlist header total sums *across* products
   (which can be mixed-currency), so it needs conversion to CAD. Table rows and chart tooltip
   stay in native currency (so a price notification isn't entangled with FX movement). Sheet
   panel shows both native currency and its FX-converted CAD equivalent.

See `context.md` for full reasoning.

## Success Criteria
- [ ] Table (Best Price / Target Price) shows native currency, correct formatting (not
      hardcoded `$`)
- [ ] Header total sums every product's best price converted to CAD
- [ ] Sheet panel shows both native currency and FX-converted CAD equivalent, per listing and
      for target_price
- [ ] Chart tooltip shows native currency (fixes existing missing-`$` bug), unaffected by FX
- [ ] Currency auto-detected from scraped page, rolled up to `Product.currency`
      (fill-only-if-null)
- [x] Manual override **API** exists (`PATCH /api/items/{id}` `{currency}`, unconditional
      overwrite, always wins over re-detection) — **UI removed 2026-08-20** (product owner
      decision, see implementation.md step 6): real usage showed auto-detection alone was
      sufficient for every product actually watched so far, so the dropdown was speculative
      complexity for a risk that hasn't materialized. Escape hatch still reachable via direct API
      call if a real misdetection ever comes up.
- [ ] `AmazonCAScraper` hardcodes `currency="CAD"`
- [ ] Alert/target comparison unchanged — native-currency-only, no FX involved
- [ ] FX rate refreshed daily, cached in `fx_rates`; stale (>24h) rate still used, with a
      stale-indicator icon shown next to FX-converted figures
- [ ] Existing mock products unaffected in practice (acceptable to start `currency = NULL`)
- [ ] Retailer badge row shows one badge per distinct retailer, not one per listing (two listings
      from the same vendor collapse to a single badge) — unrelated to currency, folded in here
      since it's the same table cell this issue is already editing
- [x] PRICE_DROP Pushover notifications show native currency, not a hardcoded `$` — missed by
      the original scope (table/sheet-panel/chart-tooltip only), found and fixed post-deploy

## Estimated Effort
- Implementation: **5 hours**
- Testing: **2 hours**
- **Total: 7 hours**
