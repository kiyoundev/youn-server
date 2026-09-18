# Issue #53: Challenges & Notes

## Potential Challenges

1. **Content-based bot-block detection is a heuristic, not a guarantee.** Matching on `"Just a moment"`/`"Access Denied"` text catches the two real cases seen so far (#52's Akamai block, the general Cloudflare pattern), but any third vendor's bot-check page (a different wording, a different service entirely) falls through to the generic `"no price found on page"` reason. That's an acceptable degrade (same message as today's total silence, just not silent), not a regression — but don't oversell this as "detects all bot-blocks." Worth a code comment saying so, so a future reader doesn't assume it's exhaustive.

2. **`HTTPScraper` is equally exposed to the silent-error path, easy to forget.** The original #52 investigation focused on `PatchrightScraper` (since that's what actually hit Crate & Barrel), but `_run_hierarchy`'s silent return is called from *both* `HTTPScraper.get_price` and `PatchrightScraper.get_price` — the fix belongs in the shared `base.py` method, not duplicated per-scraper, but it's worth explicitly testing both call paths rather than assuming Patchright-only coverage is sufficient.

3. **The `ok`+`None`-price → `error` transition changes visible behavior for existing data.** Any listing currently sitting in a stale-but-not-visibly-"failed" state (because this exact silent path was hit repeatedly in the past) will start showing as `"failed"` the next time it recurs, post-deploy. This is the intended fix, not a bug — but means a deploy could surface a small wave of "new" failures that were actually pre-existing, just invisible before. Worth mentioning if it happens, so it doesn't read as a regression caused by this deploy.

4. **Multi-retailer products lose per-line retailer labels in the Failed tooltip, same tradeoff already accepted for OOS.** This session explicitly dropped the `"IKEA: "` prefix from the OOS restock tooltip on request. Mirroring that exact format for `failedReasonLines` means a product with two *different* retailers both failing would show two unlabeled reason lines with no way to tell which is which. Consistent with the existing OOS tooltip's accepted limitation, not a new one — but flagging in case it becomes confusing once it's actually a multi-retailer product hitting it (the sheet panel's per-listing `CircleAlert` icon doesn't have this problem at all, since it's already scoped to one listing by construction).

5. **Shared production DB migration, same low-risk pattern as `0016`.** Purely additive nullable columns, no data migration, no backfill (Q5, decided) — same shape as the `restock_at` migration that already deployed cleanly this session to both local and the Pi/NAS. Low risk, but still needs the same manual `alembic upgrade head` step on the Pi after `git pull` + rebuild — easy to forget, as already happened once this session with `0016`.

## Key Differences

| Aspect | Current | Target |
|--------|---------|--------|
| Error visibility | Logged only (`exc_info=True`), lost outside the container's log retention window | Persisted on the `Listing`, visible in the app itself |
| `ok` + no price | Silent no-op, `last_scrape_status` unchanged | Explicit `"error"` with reason |
| `last_checked` source | `MAX(PriceHistory.checked_at)` — blind to `"oos"` results | `Listing.last_checked_at` — set on `"ok"`/`"oos"` |
| Failed-listing UI | Just the word "Failed" | Badge tooltip (table row) + per-listing icon+tooltip (sheet panel) |

## Rollback Plan

1. `alembic downgrade -1` reverts the `0017` migration (drops the three columns) — safe, nothing else depends on their existence at the DB level.
2. Revert the application code commit(s) — all changes are additive/branch-local (new `if` branches in `jobs.py`, new optional dataclass field, new frontend conditional rendering), no shared code path gets restructured, so a straight `git revert` should apply cleanly without conflict.
3. Redeploy (rebuild both containers, Pi + local) — no data loss on rollback since the columns being dropped were never load-bearing for anything else.
