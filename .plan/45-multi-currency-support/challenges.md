# Issue #45: Challenges & Notes

## Potential Challenges

1. **Bare-`$` ambiguity (USD vs CAD) without explicit metadata** — most sites don't mark `$` as
   `US$`/`C$`. *(Corrected 2026-08-20: the originally-cited real example, `muddygeorge.com`, is
   actually Canadian on a `.com` domain — proof TLD can't reliably split USD vs. CAD, not
   evidence for a TLD-based split. Design changed accordingly.)* Mitigation: no TLD split for
   USD/CAD — default to `CAD` whenever there's no explicit `US$`/metadata signal, since this is a
   Canadian-user app and CAD is by far the common case. `.kr` TLD is kept as a KRW-only signal
   (see below), since that one *is* backed by a real site in this codebase. Accept this will
   occasionally under-detect a real USD-only `.com` site with no `US$` marking; manual override
   exists precisely for this gap.

2. **The real Korean/KRW site in this codebase (`goyowear.kr`) doesn't mark currency on-page at
   all** — its actual regression fixture (`test_base.py:513-514`) has no `priceCurrency` in its
   JSON-LD and no `₩`/`원` symbol, just a bare `"price": "388000"`. Metadata/symbol detection
   alone would silently default this real site to CAD (wrong by ~1000x in magnitude terms).
   Mitigation: `.kr` TLD is a required detection tier, not optional — matches `goyowear.kr`
   directly (the original draft wrote `.co.kr`, which is a strict-suffix mismatch against `.kr`
   and would've missed it entirely; fixed in schema.md).

3. **`currency` staying NULL if a product's only listings never even reach the detection pass**
   — since `_extract_currency` now always resolves to a `Currency` (CAD default) rather than
   `None` on no-signal, `Product.currency` only stays NULL when every scrape fails before
   extraction runs at all (e.g. `status="error"`, no HTML parsed) — a narrower window than
   originally scoped, but not zero (a persistently-broken listing never resolves it).
   target_price/prices display as bare numbers in that window with no way to know if it's
   "resolving soon" or "permanently stuck." Mitigation unchanged: manual override is always
   available regardless of auto-detection state, same escape hatch as `Product.name`.

4. **Scope cut from the original issue text mid-planning** — the original issue specified
   per-`Listing` currency + FX conversion for cross-currency "cheapest" comparison. Product owner
   confirmed during grill-me (2026-08-19) that a single product never mixes currencies across its
   retailer listings, which removes *that* design surface (alert/target comparison stays
   native-currency-only). FX conversion came back in a narrower form later the same session — the
   watchlist header total sums across products, which *can* be mixed-currency, so it needs
   conversion to CAD. If the no-mixed-currency-per-product assumption turns out false for some
   real product later, this plan does not cover it — would need a follow-up issue.

5. **FX-converted total vs. native-currency rows can look inconsistent to the user** — the header
   total is in CAD, but individual rows are in native currency. This is deliberate (converting
   individual rows would make it impossible to tell whether a price notification reflects an
   actual price change or just FX movement — product owner's explicit reasoning), but means the
   total won't visually "add up" to the rows at a glance for a KRW/USD-mixed list. Worth a label
   or tooltip on the total (e.g. "Total (CAD)") so it doesn't read as a bug.

6. **Stale FX rate silently understates/overstates the CAD total** — using a last-known rate
   indefinitely (per product owner's explicit choice) means the total can drift from reality if
   `refresh_fx_rates` keeps failing. Mitigated by the stale icon, but the icon only *indicates*
   the problem, doesn't fix it — if the daily job stays broken for weeks, the total keeps using a
   weeks-old rate. Acceptable for now since this is a display total, not an alert.

7. **frankfurter.app's `from`/`base` param is single-currency only — `from=USD,KRW` 404s.**
   Verified live (2026-08-20): `GET /latest?from=USD,KRW&to=CAD` → `{"message":"not found"}`
   (404). The CSV-list side is `to`/`symbols`, not `from`/`base`. Correct one-request shape:
   `GET /latest?base=CAD&symbols=USD,KRW` → `{"rates":{"USD":0.72,"KRW":1003.1}}` — that's
   CAD→X, the **inverse** of what `FxRate.rate_to_cad` needs (1 unit of X in CAD), so
   `fetch_fx_rates()` must invert each value (`1 / rate`) before upserting. Getting this backwards
   would silently store a rate off by ~1000x for KRW and ~1.4x for USD, with no error to catch
   it — worth a unit test asserting the inversion against a known fixture response.

7a. **Actually hit in production, 2026-08-20 — `api.frankfurter.app` migrated to
   `api.frankfurter.dev`, now 301-redirecting every request.** Not caught by review — my earlier
   live verification of this same day used `curl -sL` (auto-follows redirects), which masked it;
   the deployed code used a plain `httpx.AsyncClient()`, which does **not** follow redirects by
   default, and `resp.raise_for_status()` treats an unfollowed 3xx as an error. Net effect:
   `refresh_fx_rates_job` ran successfully on schedule (APScheduler logged "executed
   successfully") but `fetch_fx_rates()` failed on *every single call* — `fx_rates` stayed
   permanently empty, and the watchlist header total silently dropped every non-CAD product's
   contribution to `$0` (not an error, not a crash — `toCad()` correctly returned `null` for a
   missing rate and the total just... quietly undercounted). Surfaced by the user noticing the
   CAD total didn't add up, not by any test or log alert. Fixed: point `_FRANKFURTER_URL` at the
   new host directly (`api.frankfurter.dev/v1/latest`), plus `follow_redirects=True` on the
   client as a defensive second layer against this exact failure mode recurring. Backfilled a
   regression test (`test_fetch_fx_rates_follows_redirect`) that mocks the *old* host returning a
   301 and asserts `fetch_fx_rates()` still succeeds through it.

8. **FX bootstrap gap — empty `fx_rates` table before the first successful fetch.** `GET
   /api/fx-rates` correctly returns `rates: {}, stale: true` in this state (not an error), but
   `toCad()` as originally specced (`amount * rates[currency]`) would compute `amount *
   undefined = NaN` for USD/KRW. Fixed by making `toCad()` return `null` on a missing rate and
   treating `null` as "exclude from sum" (header total) / "omit the FX suffix" (sheet panel) —
   same pattern already used for missing bestPrice and unresolved currency. Also mitigated by
   `refresh_fx_rates_job`'s `next_run_time=datetime.now(_TZ)` (matches `poll_prices`'s existing
   registration, `main.py:44-50`) — the job fires immediately on every app boot, not just on its
   24h interval, so the empty window is normally just first boot, not up to 24h.

9. **Existing (mock) `Product` rows get `currency = NULL` after migration** — acceptable per
   product owner (sample data), but worth noting: `CAD`-default display (`$` no suffix) is
   visually identical to today's hardcoded `$` for those rows *once resolved*; until their next
   scrape, they'll show bare unprefixed numbers, a temporary regression from today's always-`$`
   display. Scoped as acceptable since it's mock data, not real user data.

## Key Differences

| Aspect | Current | Target |
|--------|---------|--------|
| Price display (table) | Hardcoded `$` everywhere, chart tooltip has none at all | Currency-aware: `$X USD`, `$X` (CAD), `₩X` (KRW), bare number while unresolved |
| Header total | Raw sum of `bestPrice()` across products | Each product's best price FX-converted to CAD, then summed |
| Sheet panel price display | Native currency only (post-fix) | Native currency + FX-converted CAD equivalent shown together |
| Currency source | None — assumed USD/CAD implicitly | Detected per-scrape, rolled up to `Product.currency`, user-overridable |
| Cross-listing price comparison (alerts) | Raw `min(last_price)` | Unchanged — one currency per product, no FX needed |
| `ScraperResult` | `price`, `status`, `site_name`, `product_title` | + `currency` |
| FX rates | N/A | Daily-refreshed `fx_rates` table (USD/KRW→CAD), served via `GET /api/fx-rates`, stale-tolerant |

## Rollback Plan
1. Revert both migrations (`alembic downgrade -2`) — drops `products.currency` and `fx_rates`,
   no data loss beyond those.
2. Remove the daily `refresh_fx_rates_job` registration from the scheduler.
3. Revert frontend formatter/total changes — the 4 price-cell sites (`page.tsx:226,231,327,414`)
   revert to their original hardcoded `$` literals, `totalBestPrice` reverts to raw sum,
   retailer-badge dedup and chart-tooltip currency prop also revert.
4. Verify: existing tests pass, watchlist page renders prices/total as before.
