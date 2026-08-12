# Issue #10.2: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

Reviewed via `/code-reviewer:review` against staged changes (15 files, +1016/-142) — 2026-08-09.

### Summary

This diff wires up `#10.2`'s wishlist mutations end to end: a bulk `POST /api/items` with concurrent per-URL scraper probing and partial-success reporting, listing-URL editing that preserves id/price-history, a proxy relay for `POST`/`PATCH`/`DELETE`, and the frontend's full add/edit/pause/delete UI backed by a new toast system. Overall solid — well-tested (277 backend tests, all real behavior changes covered), consistent with the codebase's existing patterns, and each design pivot along the way is documented with its reasoning rather than left implicit. One real correctness gap worth fixing before considering this done; the rest is polish.

### Critical

None.

### Major

1. **✅ Fixed.** **`_resolve_one`'s docstring promises "never raises" — the implementation doesn't deliver that** (`backend/app/api/items.py`, `_resolve_one`). It only catches `HTTPException`:
   ```python
   async def _resolve_one(url: str, semaphore: asyncio.Semaphore) -> _ProbeResult:
       """... never raises. One bad URL ... must not cancel every other
       in-flight probe in the same batch ..."""
       async with semaphore:
           try:
               retailer, scraper_type = await _resolve_retailer_and_scraper_type(url, None, None)
               return _ProbeResult(url=url, retailer=retailer, scraper_type=scraper_type)
           except HTTPException as e:
               return _ProbeResult(url=url, error=str(e.detail))
   ```
   **Failure scenario:** today, `_resolve_retailer_and_scraper_type` only ever raises `HTTPException` (via `detect_scraper_type`'s `ValueError`→`HTTPException` conversion), so this holds in practice — but that's incidental, not enforced. Both `HTTPScraper.get_price` and `PatchrightScraper.get_price` already have broad `except Exception` internally specifically *because* scraper code deals with unpredictable external HTML/network conditions; the one function in this chain that doesn't share that defensiveness is the new concurrent-batch worker. If any future change (or an edge case already possible today — e.g. a malformed-but-Pydantic-valid URL tripping something in `_derive_retailer`/`urlparse`) raises anything other than `HTTPException` from inside that `try`, `asyncio.gather()` (no `return_exceptions=True`) propagates it immediately, **cancels every other in-flight probe in the same batch, and the whole `POST /api/items` request 500s** — the exact outcome the bulk-concurrent design was built to prevent for a single bad URL. No test currently injects a non-`HTTPException` failure into this path, which is exactly why this gap wasn't caught.
   **Fix applied:** added a second `except Exception` clause — logs unexpected errors (`_log.exception`, new module-level `_log = logging.getLogger(__name__)`) and returns a generic `failed[]` entry (`"Unexpected error while probing this URL"`, not the raw exception text — avoids leaking internal details to the API response) instead of letting it propagate. New regression test, `test_create_item_unexpected_probe_exception_does_not_cancel_siblings`: injects a `RuntimeError` into one of two concurrent probes, asserts the request doesn't raise, the good URL still creates its listing, and the bad one lands in `failed[]` — proving the "one bad URL only" guarantee now actually holds for an unanticipated exception type, not just `HTTPException`. Full suite: 278 passed.

### Minor

1. **Delete-confirmation dialog doesn't show the listing count** (`frontend/src/app/watchlist/page.tsx:475`). Currently: `"This removes all retailer listings and their price history."` — the plan's own stated design (`implementation.md` step 10) was `"This removes all N listings and their price history."` with the actual count interpolated. Not wrong, just less specific than intended — a one-line fix (`` `This removes all ${product.listings.length} listing${product.listings.length === 1 ? "" : "s"} and their price history.` ``).
2. **✅ Fixed.** **`ProductCreate`'s `_strip_name` validator is sandwiched between `target_price` and `urls`**, with the comment block explaining `urls` now appearing to dangle after an unrelated line (`backend/app/schemas/product.py`):
   ```python
   target_price: float

   _strip_name = field_validator("name")(strip_whitespace)
   # Zero or more listing URLs, created in the same request as the product
   # ...
   urls: list[str] = []
   ```
   Purely readability — Pydantic doesn't care about field/validator ordering — but moving `_strip_name` to right after `name`, or below `urls`, would keep the comment attached to the field it actually describes.
   **Fix applied:** `_strip_name` moved below `urls`, grouped with `_validate_urls` after all field declarations (matches `ListingCreate`'s existing convention — validators after fields). The `urls`-explaining comment now sits directly above `urls: list[str] = []` with nothing in between.

### Praise

- **`_ProbeResult` as a `NamedTuple` with an `error` sentinel field**, rather than raising/catching per-URL inside the `gather()` loop itself — makes the "collect outcomes, don't let one failure cancel the batch" intent explicit in the type itself, not just in a comment.
- **The `IntegrityError` race-guard comments** (both `create_item` and `update_listing`) explain *why* the race is only closable this far, not just that it's handled — genuinely useful for the next person wondering why there's a second duplicate-check layer beyond the upfront `SELECT`.
- **Test coverage of the actual behavior changes, not just happy paths** — `test_create_item_inbatch_duplicate_url_reported_in_failed`, `test_create_item_race_duplicate_url_returns_409`, and the partial-failure tests specifically assert *what survives* a partial failure (`db.commit.assert_awaited_once()`, `result.product.listings == []`), not just that an error occurred.
- **`request<T>()` in `lib/api/items.ts`** is a clean, minimal shared chokepoint — one place that turns a non-2xx response into a typed, catchable `ApiError`, used identically by all six mutation functions rather than six near-duplicate `fetch` blocks.
- **The `relay()` proxy helper's `hasBody` branching** correctly special-cases `DELETE`'s bodyless `204` response (no forced `Content-Type` on an empty body) — an easy thing to get subtly wrong and worth the explicit handling.

### Questions

- Is the `_resolve_one` exception-narrowing (Major #1) worth fixing now, or tracked as a fast-follow? Given it's a resilience gap in exactly the code path this issue's design most cares about getting right (concurrent probing, partial success), I'd lean toward fixing before calling `#10.2` done — but it's not blocking in the sense of "currently reachable via any known input."

### Verdict

**Approve.** Major #1 and Minor #2 are fixed and regression-tested (278 passed). Minor #1 (delete-dialog listing count) remains open — optional polish, not blocking.

---

## Tech Lead Review
<!-- Populated when review comments arrive (no PR for this issue — committed direct to main per user instruction; use this section for any post-hoc self-review or later feedback instead) -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
| 1 | {comment} | {File:Line} | ⬜ Open |
