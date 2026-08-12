# #36: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

**Summary:** Wires the watchlist page to real backend data and replaces its 30s poll with a Server-Sent Events push path — backend fan-out + streaming route, a Next.js streaming proxy, and frontend consumption with Web Locks-based multi-tab dedup so only one real connection exists per browser regardless of tab count. Overall assessment: solid, well-reasoned implementation with unusually thorough inline documentation of *why* each non-obvious choice was made; one real security gap surfaces as newly-live (not newly-introduced) by this change.

**Verdict**: [ ] Approve | [ ] Request Changes | [x] Comment

### Critical Issues (Must Fix)
None.

### Major Issues (Should Fix)

#### 1. [`backend/app/schemas/product.py:12`, `backend/app/schemas/listing.py`] Security: listing `url` has no server-side scheme validation, rendered as a raw `<a href>` — **FIXED**
- **Current**: `ProductCreate.url: str` (and the equivalent on `ListingCreate`) accept any string — no `AnyUrl`, no scheme allowlist. `watchlist/page.tsx:357` renders `listing.url` directly as `<a href={listing.url}>` for every listing returned by the backend.
- **Impact**: A `javascript:`-scheme (or similar) value stored as a listing's URL would execute when a user clicks it in the table. The frontend's `isValidUrl()` (http(s)-only) only gates the *add-item dialog's* client-side form — it's not enforced server-side, and doesn't apply to data already in the database.
- **Why this surfaces now, not before**: this exact rendering line existed pre-#36 too, but against hardcoded mock URLs — inherently safe. This PR is what makes the render path consume real backend data for the first time, turning a latent gap into a live one. Root cause (the schema) is pre-existing, not introduced by this diff.
- **Mitigating factor**: `POST /api/items`/`listings` is gated by `verify_api_key` — not a public unauthenticated endpoint, so exploitation requires already having API access, which narrows real-world risk on this single-user app. Not a reason to skip the fix, just why this is Major rather than Critical.
- **Fix applied**: new `backend/app/schemas/validators.py` — `validate_http_url()`, a direct backend-side mirror of the frontend's `isValidUrl` (parse via `urlparse`, require scheme in `{"http", "https"}`, raise `ValueError` otherwise — Pydantic surfaces that as a 422). Wired into both `ProductCreate` and `ListingCreate` via `field_validator("url")`, not `HttpUrl` — deliberately avoided `HttpUrl` since it returns a `pydantic_core.Url` object (not `str`) and can normalize the string (trailing slashes, host casing), which risked subtly changing the exact value stored/compared against the duplicate-URL check this same session spent a long time debugging. Verified: rejects `javascript:alert(1)`, accepts `https://...`; full backend suite (268 tests) still passes.

### Minor Issues (Nice to Have)

1. **[`frontend/src/lib/sse-leader.ts`, the final `.catch()`]** — **FIXED.** Was: re-threw any non-`AbortError` rejection without further handling, producing an unhandled promise rejection instead of surfacing it. Now: `AbortError` still returns silently (expected path), anything else logs via `console.error` and calls `setStatus("unavailable")` — surfaced through the same status path callers already handle, not thrown into the void.
2. **[`frontend/src/app/watchlist/page.tsx`, `ProductRow`'s `historyByListing` state]** — deliberately left as-is. Never prunes entries for listings removed from a product. Not currently exercisable (`#10.2`'s delete/remove mutations are still stubbed); revisit whoever wires that up.
3. **[`frontend/src/lib/sse-leader.ts`]** — **FIXED.** `LOCK_NAME`/`CHANNEL_NAME` now `"watchlist-sse-leader"`/`"watchlist-sse-relay"`, namespaced against `#37`'s future stock-tick stream adding its own channel.
4. **[`frontend/src/app/watchlist/page.tsx`]** — **FIXED.** `fetcher` moved to module scope, matching `frontend/src/app/page.tsx`'s existing convention.
5. **[`frontend/src/app/watchlist/page.tsx`, `ProductRow`]** — deliberately left as-is. `sparklineData`/`chartListings` recompute on every render, unbatched per-listing re-renders. Negligible at this app's real scale; not worth optimizing pre-emptively.

### Positive Feedback
- `ListingHistoryFetcher`'s two-layer component pattern (row + one invisible fetcher per listing) is a genuinely clean solution to a real rules-of-hooks constraint (variable listing count per product) — small, focused, correctly commented on *why* it's structured this way.
- `sse-leader.ts`'s handling of the React StrictMode × Web Locks async-grant race (the `closed` re-check inside the lock callback) reflects real, hard-won debugging during manual testing — the inline comment explaining the failure mode is exactly the kind of context that saves a future reader from re-discovering it the hard way.
- The ping-based disconnect detection in `events.py` (vs. passively polling `is_disconnected()`) is a deliberate, well-reasoned choice with the trade-off clearly documented at the point of decision, not just in a plan doc.
- Backend test coverage for the broadcast call-site is unusually thorough — `test_process_item_broadcast_uses_scraped_listing_not_cheapest_winner` specifically pins down `listing.id` vs `winning.id`, exactly the kind of subtle correctness property that's easy to silently regress later.
- `listingHistoryKey()` factored out into one shared function specifically so the SWR hook and the SSE `onmessage` mutate call can never drift into constructing the key differently — good foresight, not something most PRs bother to prevent up front.

### Questions for Author
- Is the missing server-side URL scheme validation (Major #1) intentionally deferred, or worth bundling into the migration follow-up already planned separately?
- This repo currently has zero frontend test infrastructure (no test runner configured, no existing `.test.ts` files) — the new pure functions (`mergeMinByDay`, `bucketByLocalDay`) are logic-heavy and untested, but that matches the existing project convention rather than a gap introduced here. Worth a deliberate call on whether frontend testing infra is worth introducing at some point, independent of this PR.

### Test Coverage Assessment
- [x] Happy path tested (backend: fan-out register/unregister/broadcast, disconnect detection, broadcast call-site)
- [x] Error/edge cases tested (oos/error/none-price/inactive-listing all confirmed to not broadcast; cancellation-based cleanup)
- [x] Regression-style test present (`listing.id` vs `winning.id`)
- [ ] Frontend logic (`mergeMinByDay`, `bucketByLocalDay`, `sse-leader.ts`) has no automated coverage — consistent with this repo's existing convention, not a regression
- [x] Manual test plan documented and partially executed (`implementation.md` §7) — real bugs found and fixed via that process (StrictMode/Web Locks race, Next.js 14 route-cache gap)

### Checklist
- [x] No security vulnerabilities — the one Major finding (pre-existing root cause, newly-live via this PR's real-data path) is fixed, see above
- [x] Performance is acceptable (minor unmemoized recomputation, negligible at this app's scale)
- [x] Code is readable — comment density is notably higher than average, explains reasoning not just mechanics
- [x] Tests are adequate for the backend surface touched; frontend untested but matches repo convention
- [x] Documentation is present — `.doc/architecture.md` and `.doc/keynotes.md` both updated alongside the code

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
