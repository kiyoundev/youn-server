# Issue #58: Challenges & Notes

## Potential Challenges
1. **The API is Uniqlo's internal one, not a documented contract.** Paths, the `x-fr-clientid` value and the response shape can change without notice. Mitigation: every failure returns a specific reason (the API's own message, HTTP status, variant not found), so a rotation shows up in the UI tooltip as an error, never as a wrong price. Validate that `l2s`, `stocks` and `prices` exist before reading them.
2. **Client ID rotation.** `uq.ca.web-spa` comes from the public `main-*.js` bundle (config key `clientID` for the UQ brand). If it changes, the API answers 400 `invalid or missing client id`. Recovery: re-read the bundle (DevTools → Network → filter `l2s` shows the header directly) and update `UNIQLO_CLIENT_IDS`. No code change otherwise.
3. **Akamai.** The page loads Akamai's sensor script, and #52 shows a site can allow one client and deny another. The API worked from both the Mac and the Pi (plain HTTP, one request each), but that doesn't promise it keeps working at six-hour polling. Mitigation if it starts denying: surface "Akamai bot-block" through the existing reason path (#53) and revisit pacing in #52's terms. Not solved here.
4. **The add flow resolves the URL first.** `_resolve_final_url` HEADs (then GETs) the page before routing. Verified from the Pi: a HEAD on a Uniqlo product URL returns 200, so this works and `items.py` is unchanged. If Uniqlo ever starts denying it, adding a Uniqlo URL would fail with "URL could not be resolved" even though the API works; the fix then would be to skip resolution for `RETAILER_MAP` hosts that have no shortlinks.
5. **Stock status values.** Across the two captures (33 variants), only `IN_STOCK` and `STOCK_OUT` appear. Variants with a quantity of 4 still report `IN_STOCK`, so no separate low-stock code has been seen. The rule "in stock when `quantity > 0` and `statusCode != STOCK_OUT`" copes with one if it exists. `transitStatus` (`WILL_TRANSIT`) appears on some in-stock variants and is ignored.
6. **Prices exclude tax (`taxPolicy: EXCLUSIVE`).** Matches what uniqlo.com/ca displays and how other retailers' prices are tracked here; no conversion.
7. **Stale variant.** A color/size that Uniqlo later drops returns `error` with the variant in the reason, rather than quietly tracking another variant (unlike the Shopify stale-ID fallback we chose to leave alone).

## Key Differences
| Aspect | Current | Target |
|---|---|---|
| Routing | Generic probe → HTTP, then Patchright, both fail | `RETAILER_MAP` → `UniqloScraper`, no probe |
| Data source | Page HTML (no extractor matches) | Commerce API, one call per listing |
| Variant | Ignored | Exact color/size from the URL |
| Failure reason | "no price found on page" / add rejected | API message, HTTP status or variant not found |

## Rollback Plan
1. Remove `"uniqlo.com": UniqloScraper` from `RETAILER_MAP` (Uniqlo goes back to the old generic path and fails as before; nothing else is affected).
2. Verify: `pytest tests/scraper` passes, and a non-Uniqlo listing still scrapes. No migration or data change to undo.
