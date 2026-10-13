# Issue #60: Challenges & Notes

## Potential Challenges
1. **Layout drift** — Amazon's markup differs between the accordion and plain layouts and will change again. Mitigation: an ancestor walk anchored on `#add-to-cart-button`, then `error` with a specific reason. A wrong price is worse than a visible error icon.
2. **Plain layout seen once** — captured on `B073S5JHRV` (2026-10-12): price in `.apex-pricetopay-value .a-offscreen`, no `customerVisiblePrice` inputs in the fragment. Step 1 still re-captures it through the Pi's scraper, since the browser view may differ from what the headless scraper receives.
3. **Duplicate element ids** — `corePrice_feature_div`, `apex_offerDisplay_desktop`, `addToCart_feature_div` appear in both the new and used rows. Never select by those ids; walk up from `#add-to-cart-button`.
4. **Misleading numbers outside the new buy box** — the used row's `twister-plus-price-data-price` holds the new price, and the "Other sellers" box shows "New (3) from $…" / used prices. The old page-wide scan could read any of these (a plausible cause of the original false drop). Only read inside the ancestor found from the button.
4a. **`[data-pricetopay-label]` is unsafe, not dead** — it exists in the title price block, reflects the *featured* offer (the used price on a used-only page) and, on a discounted offer, its text is `"$X with N percent savings"`, which `_parse_price` turns into garbage (`52.135`, `1299.0012`). Dropping it also fixes the existing discounted-price corruption. Do not reintroduce it.
4b. **Empty `.apex-pricetopay-value` nodes** — the title price block has them (text lives in the label span). Skip empty text and read only inside the ancestor of `#add-to-cart-button`.
5. **Price injected after `load`** — parsing `page.content()` would miss it. Evidence so far says the price is server-rendered (it is in the pasted HTML), but the Pi capture in step 1 confirms it.
6. **Used price only from the used-only box** — "No featured offers" pages show no used price even if used offers exist behind "See all buying options". Accepted.
7. **`error` is not `oos`** — a found new buy box with an unreadable price must not report `oos` (it would trigger a false restock push on the next good scrape). It reports `error`, which per #61 also produces no restock event on `error → ok` (known limitation).
8. **Currency** — the amount input carries `currencyCode`; the scraper keeps returning CAD, and treats a non-CAD code as an `error` rather than guessing.
9. **Test helper rewrite** — `_run_get_price` currently patches `_find_price_text`; removing that method changes every Amazon `get_price` test.

## Key Differences
| Aspect | Current | Target |
|--------|---------|--------|
| Price source | browser locators, page-wide fallback | Python parse of `page.content()`, scoped to the new buy box |
| Not found | falls back to any `$` on the page | `error` with a specific reason |
| Used price | ignored | nullable `Listing.used_price`, info icon only |
| Tests | price read never exercised | real-HTML fixtures for four page states |

## Rollback Plan
1. Revert the code (`patchright_scraper.py`, `jobs.py`, API, frontend).
2. `alembic downgrade 0019` (drops `used_price`; no other data depends on it).
3. Confirm polls still run and `\d watch_items` has no `used_price`.
