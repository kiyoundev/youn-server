# Issue #45: Implementation

## Steps

### 1. Backend — Detection
- [x] `ScraperResult` (`result.py`) — add `currency: Literal["USD","CAD","KRW"] | None = None`
- [x] `base.py` — add `_extract_currency(soup, url, jsonld_scripts)` per corrected priority order
      in `schema.md`: explicit metadata/symbol → `USD`/`KRW`; `.kr` TLD → `KRW` (not `.co.kr` —
      matches the real `goyowear.kr` case); everything else defaults to `CAD` (no `.ca`/USD TLD
      split — `muddygeorge.com` proved TLD unreliable for that). `None` only on genuine
      extraction failure, not "no signal." Wire into `_run_hierarchy` alongside the existing
      site_name/product_title pass (same `dataclasses.replace(...)` call, one extra kwarg)
- [x] `patchright_scraper.py` — `AmazonCAScraper` hardcodes `currency="CAD"` on its returned
      `ScraperResult` — not because CAD needs special-casing (it's the default now), but because
      this scraper runs its own dedicated extraction path and never calls
      `_run_hierarchy`/`_extract_currency` at all

### 2. Backend — Data Layer
- [x] Migration `0014_product_currency.py` — add nullable `products.currency`
- [x] `models/product.py` — add `currency: Mapped[str | None]` column
- [x] `schemas/product.py` — add `Currency` type alias, add `currency` to `ProductCreate` /
      `ProductUpdate` / `ProductResponse`
- [x] `scheduler/jobs.py` — in the same guarded block that fills `product.name` from
      `scrape.product_title` (issue #44), add: `if scrape.currency and product.currency is
      None: product.currency = scrape.currency`. Since step 1 made `_extract_currency` always
      resolve to a concrete value (CAD default, never `None`) and `AmazonCAScraper` also always
      sets `"CAD"`, `scrape.currency` is truthy on essentially every `status="ok"` scrape — this
      fill effectively always fires on a product's first successful scrape.
      `RetailerRouter.get_price()` confirmed a pure pass-through (no `ScraperResult`
      reconstruction), so `scrape.currency` survives the dispatch unchanged.
- [x] `api/items.py` — 3 separate edit sites, not just "confirm the PATCH path":
      1. `create_item` (`:247`) — `Product(name=body.name, target_price=body.target_price)` needs
         `currency=body.currency` added, or `POST` can never set currency at creation.
      2. `update_item` (`:395-403`) — same truthy-presence pattern already used for
         `name`/`target_price`/`active` (`if body.X is not None: product.X = body.X`, not
         `exclude_unset`): add `if body.currency is not None: product.currency = body.currency`
         — unconditional overwrite when present, manual override always wins, no new pattern
         needed.
      3. `_build_product_response` (`:175-186`) — builds `ProductResponse(...)` **field-by-field
         manually**, not via `model_config = {"from_attributes": True}` (that config is set but
         unused by this builder). Adding `currency` to the `ProductResponse` schema alone does
         nothing — must also add `currency=product.currency` here, or every response either 422s
         (no field default) or silently always reports `None` (with a default), regardless of
         the real DB value. Easy to miss since it's the output side, not the PATCH input side.

### 3. Backend — FX Rates
- [x] `models/fx_rate.py` (new) — `FxRate` model
- [x] Migration `0015_fx_rates.py` — create `fx_rates` table
- [x] `services/fx.py` (new) — `fetch_fx_rates()` calls `GET /latest?base=CAD&symbols=USD,KRW`
      (one request; **not** `from=USD,KRW` — confirmed live that 404s, `from`/`base` is
      single-currency only) and **inverts** each returned rate (`1 / rate`) before returning, since
      `base=CAD` gives CAD→X not X→CAD. `refresh_fx_rates(session)` (upserts, no-ops on fetch
      failure)
- [x] `main.py` (`lifespan`, alongside the existing `poll_prices` registration) — register
      `refresh_fx_rates_job` matching the *exact* pattern already used there:
      `scheduler.add_job(refresh_fx_rates_job, "interval", hours=24, next_run_time=datetime.now(_TZ))`.
      This is `"interval"`, not `"cron"` — matches `poll_prices` (`main.py:44-50`), the only
      existing scheduled job in this codebase. Fires once immediately at every app boot (via
      `next_run_time`), then every 24h **from that boot time** — not anchored to midnight. A
      container restart at 3:47pm means it fires at 3:47pm daily thereafter, not 12:00AM.
      Deliberate: matches the one existing scheduling convention here, and this is a low-stakes
      display cache (not an alert path) where drift off midnight doesn't matter. The
      `next_run_time=datetime.now(_TZ)` immediate-fire already covers the empty-table bootstrap
      case — **no separate startup call needed**, it'd be a redundant second fetch on every boot.
- [x] `api/fx.py` (new) — `GET /api/fx-rates`, reads `fx_rates` table, computes `stale` (any row
      >24h old or missing entirely)

### 4. Frontend — Display (native currency, table)
- [x] `watchlist/page.tsx:215-219` — retailer badges: currently one `<Badge key={listing.id}>`
      per listing, no dedup — two listings on one product sharing the same `retailer` string
      (different URLs, same site; `Listing.url` is unique but `retailer` isn't) render two
      identical badges. Dedup by `retailer` text before mapping:
      `Array.from(new Set(product.listings.map((l) => l.retailer))).map((retailer) => <Badge
      key={retailer}>{retailer}</Badge>)` — **not** `[...new Set(...)]`: spread-iterating a `Set`
      fails this project's TS target (`TS2802`, confirmed via `tsc --noEmit`); matches the
      `Array.from(new Set(...))` pattern already used in this same file (`mergeMinByDay`).
      Unrelated to currency, but same block this step is already touching — folded in here
      rather than a separate issue.
- [x] `lib/api/items.ts` — add `currency: Currency | null` to `Product` type; add `FxRates` type
      + `getFxRates()` API call
- [x] `lib/format.ts` (not inline in `page.tsx` — shared with `product-price-chart.tsx`, a `ui/`
      component that shouldn't import from `lib/api/`) — new `fmtPrice(amount, currency)`
      helper. Today's `$` was 4 separate inline literals, not one shared function to "replace":
      Best Price cell `` `$${best.toFixed(2)}` `` (`page.tsx:226`), Target Price cell
      `` `$${product.target_price.toFixed(2)}` `` (`:231`), sheet-panel target_price (`:327`),
      sheet-panel per-listing price (`:414`) — all 4 now call `fmtPrice(value, product.currency)`.
      `fmtValue` (`:87`, used only by the header total) is untouched — the header total is always
      post-FX CAD already, so its plain `$` is already correct output, just fed a converted
      number instead of a raw sum (see step 5).
      - `USD` → `` `$${amount.toFixed(2)} USD` ``
      - `CAD` or `null` (default, matches today's behavior for the unresolved window) → `` `$${amount.toFixed(2)}` `` — no suffix
      - `KRW` → `` `₩${Math.round(amount).toLocaleString()}` `` — no decimals
      - Native currency, **not** FX-converted — so a price notification is legible as "the price
        changed," not entangled with FX movement
- [x] `product-price-chart.tsx` — `ProductPriceChartProps` gained a `currency` field, threaded
      through from `page.tsx:297`'s `<ProductPriceChart .../>` call. `ChartTooltipContent`'s
      `formatter` prop, once supplied, replaces the tooltip row's *entire* content (indicator dot
      + name + value — confirmed in `chart.tsx`), not just the value text — the new `formatter`
      replicates that default "dot"-indicator row exactly, just calling `fmtPrice()` for the
      value instead of a bare `.toLocaleString()`. Fixes the existing missing-`$` tooltip bug;
      native currency, unaffected by FX.

### 5. Frontend — FX-Converted Total & Sheet Panel
- [x] `watchlist/page.tsx` — fetch `/api/fx-rates` once on page load (alongside existing
      products fetch), via `useSWR<FxRates>("/api/proxy/fx-rates", () => getFxRates())` — reuses
      `getFxRates()` (added in step 4, unused until now) rather than the raw `fetcher` products
      use, since it gives typed `ApiError` handling for free
- [x] `toCad(amount, currency, rates) -> number | null` helper (`lib/format.ts`, alongside
      `fmtPrice`) — `CAD`/`null` currency passes `amount` through unchanged; `USD`/`KRW`
      multiplies by `rates[currency]` **only if that key exists** — `rates` can legitimately be
      `{}` (bootstrap: table empty before the first successful `refresh_fx_rates`, see
      schema.md), and `rates[currency]` on a missing key is `undefined`, so an unguarded multiply
      produces `NaN`. Returns `null` when the needed rate isn't present — never `NaN`. Also added
      `fmtCadEquivalent()` (formats the sheet-panel `"(~$29 CAD)"` suffix, `null` when there's
      nothing useful to show — already-CAD/unresolved, or missing rate)
- [x] `totalBestPrice` (header sum, previously raw `sum(bestPrice(product))`) — converts each
      product's best price to CAD via `toCad()` before summing; a `null` result (missing
      bestPrice **or** missing rate) contributes `0` to the sum, same as the existing
      null-bestPrice handling — never lets a `null`/`NaN` poison the total. "Total" label also
      gets a `"(CAD)"` suffix (challenges.md #5) since the total no longer visually "adds up" to
      native-currency rows for a mixed-currency list.
- [x] Stale-indicator icon (`ClockAlert`, `lucide-react`) next to the header total when
      `fxRates.stale === true` (this already covers the bootstrap case — `stale` is `true`
      whenever a row is missing entirely, per schema.md). Native `title` attribute for the hover
      explanation — no new UI dependency for a single icon.
- [x] Sheet panel — per-listing price rows and target_price display show both native currency
      (existing formatter) and FX-converted CAD equivalent via `fmtCadEquivalent()`, e.g.
      `₩30,000 (~$29 CAD)`; `null` (already-CAD, unresolved, or missing rate) **omits** the
      suffix entirely rather than rendering `(~$NaN CAD)`. Stale icon reused here too when
      applicable.

### 6. Frontend — Manual Currency Override
**Reverted 2026-08-20 (product owner decision) — UI pulled, API field kept.** Originally built as
a `DropdownMenu` picker (USD/CAD/KRW) next to target_price in the sheet panel; removed after
review. Reasoning: in actual live use, both real products (goyowear, Amazon) resolved correctly
through auto-detection alone — the override was never used to *fix* a wrong detection, only once
as a debugging shortcut while unrelated bugs (frankfurter.app redirect, Amazon scraper flakiness)
were being chased. With only 3 currencies and a real failure mode (USD-only `.com` site with no
`US$` marking defaults to CAD) that hasn't actually occurred yet for this user's retailer list,
the dropdown was real UI surface area (a component, a commit-immediately click handler, its own
test coverage) paid for a risk that's still theoretical. The backend PATCH field
(`ProductUpdate.currency`, `ProductUpdatePayload.currency` in `lib/api/items.ts`) stays — near-
zero marginal cost, and still the generic "fix wrong data by hand" escape hatch if a real
misdetection ever does show up; it's just not surfaced in the UI right now. If that changes,
re-adding the dropdown is a small, isolated diff (see git history for this file around
2026-08-20 if resurrecting it — the sheet panel's `flex items-center gap-1` block just before the
target_price edit-pencil `Button` is where it lived).
- [x] `watchlist/page.tsx` — `DropdownMenu` picker removed; `CURRENCY_OPTIONS` constant and its
      now-unused `Currency` import removed alongside it
- [x] `lib/api/items.ts` — `ProductUpdatePayload.currency?: Currency` **kept**, PATCH support
      still fully wired backend-side (`api/items.py`'s unconditional-overwrite branch, untouched)

### 7. Testing & Validation
- [x] Backend: unit tests for `_extract_currency` — og:price:currency, JSON-LD priceCurrency
      (incl. unsupported-code fallthrough), `₩`/`원`/`US$` symbol cases, `.kr` TLD with no other
      signal (the real `goyowear.kr` case), bare-`$` defaults to `CAD` regardless of TLD (the
      corrected design — no `C$`/`CDN$`/`.co.kr` branches, no `None`-on-no-signal; superseded by
      the muddygeorge/goyowear correction, see challenges.md #1-2), metadata-wins-over-TLD
      precedence. 10 tests, `test_base.py`.
- [x] Backend: `AmazonCAScraper` always returns `currency="CAD"` — correction: `test_patchright.py`
      had **zero** tests for `AmazonCAScraper` at all before this (not just currency — no
      coverage of its success path, title inference, or anything else), so "covered indirectly"
      was wrong when first written here. Added 2 real tests:
      `test_amazon_ca_scraper_success_always_includes_currency_cad` and
      `test_amazon_ca_scraper_error_path_leaves_currency_none` (confirms the hardcode is
      success-path-only, matching `ScraperResult.currency`'s "None means _run_hierarchy never
      ran" contract from `result.py`).
- [x] Backend: `process_item` fills `Product.currency` only when null; a manual override via
      PATCH is never clobbered by a subsequent scrape — `test_jobs.py`'s
      `test_process_item_fills_product_currency_when_null` /
      `test_process_item_does_not_overwrite_existing_product_currency` (the guard is a plain
      `is None` check, so "already set" covers both auto-detected and manually-overridden
      identically — no separate PATCH-then-rescrape test needed). PATCH overwrite itself covered
      by `test_items_routes.py`'s `test_update_item_currency_overwrites_unconditionally`.
- [x] Backend: `refresh_fx_rates` upserts on success, no-ops (keeps old rows) on fetch failure —
      `test_fx.py`.
- [x] Backend: `GET /api/fx-rates` reports `stale=true` when a row is >24h old or missing —
      `test_fx_routes.py`, plus a 23h-not-stale boundary test.
- [x] Backend: `fetch_fx_rates()` follows redirects — added after a real production incident
      (2026-08-20, api.frankfurter.app migrated to api.frankfurter.dev; challenges.md #7a) —
      `test_fetch_fx_rates_follows_redirect`.
- [x] Frontend: format helper / `toCad()` unit tests — **skipped, deliberately** (product owner
      decision, 2026-08-20). No test framework exists in this frontend at all; standing one up
      for 3 small pure functions was judged not worth the new tooling/dependency for a no-CI,
      manual-verification solo project. Already exercised live through this session's manual
      debugging (KRW display, header total, stale icon all directly observed working). See note
      below.
- [x] Manual: KRW product displays `₩` with no decimals in the table — confirmed live
      (goyowear screenshot, `₩388,000`)
- [ ] Manual: sheet panel shows both `₩X` and `~$Y CAD` — not yet confirmed live
- [x] Manual: header total sums correctly across mixed-currency products — **was broken**
      (frankfurter.app redirect incident, challenges.md #7a — total silently dropped the KRW
      product's contribution to $0), now fixed; not yet re-confirmed live post-fix
- [ ] Manual: currency dropdown override persists and blocks re-detection from changing it back —
      not yet confirmed live
- [x] Manual: stale icon appears when FX data is unavailable — confirmed live (same incident,
      `stale: true` correctly showed while `fx_rates` was empty)
- [ ] Edge case: product with zero listings / not-yet-scraped — currency stays `null`, bare
      number displayed, no crash; excluded or treated as CAD (0 impact) in total sum — not yet
      confirmed live

**Frontend test framework decision (resolved 2026-08-20):** skip — no vitest/jest stood up for
this issue. `fmtPrice`/`toCad`/`fmtCadEquivalent` (`lib/format.ts`) stay covered by manual/live
verification only, matching this repo's existing convention.

### 8a. Backend — PRICE_DROP notification currency (found 2026-08-20, post-deploy)
- [x] `app/consumers/notify.py`'s `_format_price_drop` hardcoded `$` regardless of
      `product.currency` — missed by the original acceptance criteria (named table/sheet-panel/
      chart-tooltip specifically, not the Pushover notification body). A KRW product's alert
      would have read "Now $388000.00" — the raw KRW number with a `$`, implying ~$388k USD/CAD
      instead of ~₩388,000. Trigger logic itself (`process_item`'s `cheapest <=
      product.target_price`) was already correct/untouched — native-currency-only, no FX, same
      as always; this was purely a display bug in the message text.
- [x] New `app/services/format.py` — `format_price(amount, currency)`, a backend-side mirror of
      `lib/format.ts`'s `fmtPrice()` (same 3 branches: KRW no-decimals, USD-with-suffix,
      CAD/None passthrough) so the Pushover notification and the watchlist UI never disagree
      about how a given `(amount, currency)` pair reads.
- [x] `notify.py` — both `payload["price"]` and `product.target_price` now go through
      `format_price()`.
- [x] Tests: `test_format.py` (5 cases), `test_notify.py`'s new
      `test_format_price_drop_uses_product_currency_not_hardcoded_dollar`. Also had to add
      `currency=None` to 2 pre-existing `SimpleNamespace` product fixtures
      (`test_notify.py`, `test_dispatcher.py`) that would've hit `AttributeError` the moment
      real code started reading `product.currency`.

### 8. Cleanup
- [x] Remove/update any stale `$` literals left in place after the formatter swap — only 2
      legitimate `$` uses remain: `fmtValue()` (header total, deliberately not on `fmtPrice`
      since it's always post-FX CAD already) and the target-price `InputGroupText` addon (new
      code, picks `₩`/`$` by currency)
- [x] Run backend `pytest` and frontend lint — 390/390 backend tests pass, `next lint` and
      `tsc --noEmit` both clean
