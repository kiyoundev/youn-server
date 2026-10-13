# Issue #64: Challenges & Notes

## Potential Challenges
1. **Identity-map trap (#48).** A plain `session.get(Product, ...)` in oos/error is safe only because those branches return before the locked `select(...).with_for_update()`. The shared helper must take `product` as a parameter so each caller picks its read; the `ok` path keeps the locked one. The anomalous "ok with no price" branch also returns early, so it uses the plain read.
2. **Wrong permanent name.** Name fill is first-write-wins. Guard: generic path withholds name/retailer on errors; Amazon returns no title for redirected variants or pages without `#productTitle`; bot blocks carry nothing.
3. **Amazon retry staleness.** `failure_reason` persists across attempts; the matching `failure_title` must be set in the same place so a title from one attempt isn't paired with another attempt's error.
4. **IKEA name may not exist.** Fragment payload may not expose one. Mitigation: live-fetch before coding; fall back to currency-only.
5. **Retailer fill moves below the lock on `ok`.** Same transaction, no race implication, but keep the curated-host exclusion intact.

## Key Differences
| Aspect | Current | Target |
|--------|---------|--------|
| Metadata applied on | `ok` only | `ok`, `oos`, `error`, anomalous-ok |
| Amazon title source | Playwright call, success only | Parsed soup, every attempt |
| Generic error metadata | all fields | currency only; none on bot block |
| Deviation from issue text | block-detector-only guard | + name/retailer withheld on any generic error |

## Rollback Plan
1. Revert the commit; no migration or data change involved.
2. Names already filled stay (correct ones); a wrong one is edited in the sheet.
