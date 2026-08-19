# Issue #48: Review

## AI Review
_Run via `/code-reviewer:review` on staged changes, 2026-08-19._

### Summary
This changeset does three linked things: (1) consolidates pause/resume from a per-listing `Listing.active` column to a single `Product.active` column (migration `0012`, model/schema/route/frontend updates), (2) groups `poll_prices`'s scrape query by product and scrapes each product's listings concurrently under a bounded semaphore (reusing #41's gather-with-semaphore shape), and (3) fixes a genuine double-alert race by switching `process_item`'s alert-dedup Product read to `SELECT ... FOR UPDATE`. Overall: solid, well-reasoned engineering — the scope grew substantially from the original issue but each expansion is justified in the plan docs and the code matches the stated design. **Approved**, with a few things worth a look before merge.

### Critical
None found.

### Major
- **`.doc/issues.md` change is unrelated to this diff, bundled in anyway.** The one-line change marking `#47` done has nothing to do with #48's actual work — leftover drift from an earlier session, never committed. Worth splitting into its own commit rather than folding it in. **Not fixed as part of this pass** — a git-staging decision, not a code fix; left for commit time.
- **The concurrency-race fix has no automated test that would catch a regression of the fix itself** — by design, and correctly reasoned through (see `challenges.md` #4: no mock can simulate the real race in a single-threaded event loop). What *would* catch a full revert: the SQL-shape assertion in `test_process_item_writes_history_and_price_drop_event` (`_for_update_arg is not None`). Worth keeping in mind for future reviewers touching `process_item`. **Not a code fix** — acknowledged risk, not actionable here.

### Minor — fixed
- [x] `poll_prices`'s per-product `try/except Exception` around `_gather_bounded_scrapes` was unreachable in practice with no comment explaining why (`_bounded_process_item` never raises). Added a one-line comment.
- [x] `asyncio.gather()`'s sibling-tasks-not-auto-cancelled-on-failure gotcha, now doubled in usage (both #41's dispatch and every `poll_prices` cycle) — added a comment noting the "never raises" contract is what makes this safe, so a future reader doesn't need to rediscover the gotcha from scratch.
- [x] `update_listing`'s docstring led with "Partial update" even though only `url`/`retailer` remain — reworded for clarity now that `active` is gone.

### Praise (from the review, worth keeping in mind)
- The identity-map hazard around `with_for_update()` is exactly the kind of bug that's easy to introduce and hard to catch in review — called out inline at the point of use, not just in a design doc.
- The `_gather_bounded_scrapes`/`_dispatch_first_scrapes` split solves the `close_if_idle()` call-count mismatch with a minimal extraction, not a bigger refactor.
- Dropping the misleading concurrency-race unit test after empirically proving it passed identically with and without the fix, rather than shipping false coverage.
- Migration `0012`'s docstring embeds the actual diagnostic query run against production data, not just a claim it was checked.
- Live double-alert verification actually happened this session against real Postgres — not deferred.

### Verdict
**Approve.** No correctness issues beyond the two Major items above, both hygiene/acknowledgment rather than bugs.

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
