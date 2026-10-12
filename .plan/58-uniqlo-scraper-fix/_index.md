# Issue #58: Uniqlo Scraper Fails — Diagnose and Fix

## PR / Branch
- **Branch:** `fix/58-uniqlo-scraper-fix`
- **PR Title:** `main | fix - 58 - Uniqlo scraper via commerce API`
- **Note:** this repo doesn't actually use branches (solo project, direct commits to `main` — see `.doc/issues.md`'s own numbering being the real ticket system here). Branch/PR fields above are nominal, kept for consistency with this skill's template — commit directly to `main` unless a branch is specifically wanted for this one.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | 🟡 Built + unit-tested (371 passing), awaiting deploy + live verification | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [ ] Root cause written into `.doc/issues.md` #58 with evidence: not a bot-block; the price lives in an inline `window.__PRELOADED_STATE__` blob and Uniqlo's own commerce API, neither of which any existing extractor reads
- [ ] `UniqloScraper` registered in `RETAILER_MAP` for `uniqlo.com` — strict, no fallback, no browser (same convention as `IKEAScraper` / `AmazonCAScraper`)
- [ ] A Uniqlo URL with `colorDisplayCode` + `sizeDisplayCode` tracks exactly that variant: in stock → `ok` + price; sold out → `oos` (price kept, like IKEA)
- [ ] A URL without color/size: `oos` only if every variant is sold out, otherwise `ok` at the first in-stock variant's price; color-only applies the same rule within that color
- [ ] Price is `prices[l2Id].promo.value` when a promo exists, else `base.value`; currency comes from the API (`base.currency.code`)
- [ ] Canada only: any other region (`/us/`, `/jp/`, …) fails with a specific `unsupported Uniqlo region` reason, never a guessed price
- [ ] Every failure carries a specific `last_scrape_error` (API error message, HTTP status, variant not found) — never "no price found on page"
- [ ] Regression tests in `tests/scraper/` built from trimmed real API responses (in stock, sold out, promo)
- [ ] Live-verified on the Pi with the blouson (in stock, color 67 / size 004) and the sold-out example (E488599-000, color 38 / size 003)

## Estimated Effort
- Implementation: **2 hours**
- Testing: **1 hour**
- Live verification + `issues.md` update: **0.5 hours**
- **Total: ~3.5 hours** (diagnosis already done during planning)
