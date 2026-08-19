# Issue #44: Implementation

## Steps

### 1. Data Layer — migration + models + schemas — ✅ done
- [x] Created `backend/alembic/versions/0013_product_name_nullable.py` (revises `0012`).
- [x] `backend/app/models/product.py` — `name: Mapped[str | None] = mapped_column(String, nullable=True)`.
- [x] `backend/app/schemas/product.py` — `ProductCreate.name: str | None = None` (custom validator also coerces an explicit `""` to `None`, not just an omitted field); `ProductResponse.name: str | None`; `ListingFailure` gains `retailer: str` (required, not optional — see next bullet for why that had to be handled now).
- [x] **Same lesson as #48, applied proactively:** making `ListingFailure.retailer` required broke every existing construction site in `create_item` (4 of them) immediately — pulled forward from step 4 rather than left broken until then. Each now populates `retailer`: the two pre-resolve failure paths (in-batch duplicate, existing-URL duplicate) derive it from the raw pasted URL's hostname (`_derive_retailer(_hostname_of(url))`); the post-resolve probe-failure path does the same (resolution itself failed, so no successful hostname to use); the post-resolve URL-collision path uses `result.retailer` directly (already populated by then, more accurate than re-deriving) with the same derivation as a fallback.
- [x] Migration run locally and round-tripped (`upgrade head` → `downgrade -1` → `upgrade head`, all clean) after rebuilding the container (same "container has old image" gotcha as `#48` — rebuild before `alembic exec`, every time). Confirmed nullable via `\d products` on the real DB. Round-trip didn't exercise the `'Untitled'` backfill path itself (no products currently have `NULL` names to backfill) — acceptable, matches "purely additive, no data to lose" reasoning already in `schema.md`.
- [x] Full backend suite: 313 passed (no existing test asserts on `ListingFailure`'s exact field set, so the new required field didn't need test updates to stay green — though step 5's testing pass should still add explicit coverage for it).

### 2. Scraper layer — `ScraperResult` + extraction
- [ ] `backend/app/services/scraper/result.py` — add `site_name: str | None = None`, `product_title: str | None = None`.
- [ ] `backend/app/services/scraper/base.py`:
  - Generalize `_find_jsonld_product` into a `_find_jsonld_type(data, target_types: set[str])` helper; keep `_find_jsonld_product` as a thin wrapper calling it with `{"Product"}` (no existing call sites change).
  - Add `_extract_site_name(soup)` and `_extract_product_title(soup)` module-level helpers (og tag → JSON-LD → `<title>` heuristic, per `schema.md`'s exact snippets).
  - Add `_last_title_segment`/`_first_title_segment` small string-splitting helpers (common separators: `–`, `—`, `|`, `-`; `None` if no separator found — don't guess wrong on an ambiguous single-segment title).
  - Restructure `_run_hierarchy`: parse `soup` unconditionally (moved up, before the Shopify branch short-circuits), run the two new extraction passes on whatever `ScraperResult` the existing 4-method price hierarchy ends up returning, attach via `dataclasses.replace(...)`.
- [ ] `backend/app/services/scraper/patchright_scraper.py` — `AmazonCAScraper` gets `_find_product_title(page)` (own try/except, non-fatal), called once per successful scrape in `get_price`, result attached to its `ScraperResult` construction.

### 3. `process_item` — the fill logic itself — ✅ done
- [x] Moved `_derive_retailer`/`_hostname_of` from `api/items.py` to `services/scraper/router.py` (avoids the import cycle flagged in `challenges.md` #1 — `router.py` already owned `RETAILER_DISPLAY_NAMES`, the more natural home anyway). `items.py` now imports both from there; `RetailerRouter.get_price`'s own inline hostname parse simplified to reuse `_hostname_of` too, same file. Confirmed no cycle: `import app.api.items; import app.scheduler.jobs` both succeed.
- [x] `backend/app/scheduler/jobs.py` — `listing.retailer` fill added right after a successful scrape (guarded: only while `listing.retailer == _derive_retailer(hostname)`), doesn't touch `product` at all.
- [x] `product.name` fill added at the existing locked `product` read (`#48`'s `with_for_update()`), guarded: only while `product.name is None` — piggybacks the read, no second query.
- [x] Both fills are no-ops when their guard doesn't hold or `scrape.site_name`/`scrape.product_title` is `None` — confirmed by the full suite staying green untouched (313 passed) — no existing test's `ScraperResult` mocks set either field, so every existing test naturally exercises the no-op path.

### 4. Bulk-add failure toast + frontend name handling — ✅ done
- [x] `backend/app/api/items.py` — done in step 1 (pulled forward, `ListingFailure.retailer` was a required field that broke every construction site immediately).
- [x] `frontend/src/lib/api/items.ts` — `ListingFailure.retailer: string`; `Product.name: string | null`; `ProductCreatePayload.name?: string` (optional).
- [x] `frontend/src/app/watchlist/page.tsx`:
  - `canSubmitNewItem` no longer requires a non-blank name.
  - `handleAddItem` sends `name: trimmedName || undefined` (omitted when blank, not sent as `""`); both post-create toasts (success, partial-failure) use `product.name ?? "item"` as a fallback display name, since inference runs async and may not have completed by the time the create response returns.
  - Failure toast: `f.retailer (f.detail)` instead of the raw URL.
  - **Every other `product.name` render site found and fixed** (more than the original file list called out): table cell, sheet title (both the `sr-only` editing-state one and the visible one), delete-confirmation dialog title — all fall back to `"Untitled"`. The sheet's edit-name button now seeds the input with `product.name ?? ""` (was a TS type error otherwise — `editName`'s action type requires `string`, not `string | null`).
  - **Real crash caught, not just a type error:** the products-list search filter did `product.name.toLowerCase()` unconditionally — would throw on any product with a `null` name. Fixed to `(product.name ?? "").toLowerCase()`.
  - A separate `WatchlistTile` dashboard component also has a `.name` field, but it's a standalone mock-data component with its own local `WatchlistItem` type (not sourced from `lib/api/items.ts`) — confirmed unaffected, left untouched.
- [x] `npx tsc --noEmit`: clean. Backend suite: 313 passed (unaffected, confirmed anyway).

### 5. Testing & Validation
- [x] Unit: `_extract_site_name`/`_extract_product_title` — 21 new tests in `test_base.py`: `_split_title` edge cases (single separator, no separator, ambiguous multiple separator types, empty segments), each extraction function's og-tag/JSON-LD/`<title>`-fallback priority order and no-signal case, plus `_run_hierarchy` attaching both fields alongside whichever price method wins.
- [x] Unit: `process_item`'s two fill guards — 4 new tests in `test_jobs.py`: retailer fills when the listing's URL-derived hostname fallback is still untouched, stays put when it's been manually edited to something else; product.name fills when `NULL`, stays put when already set.
- [x] Unit: `ListingFailure.retailer` — extended 5 existing tests in `test_items_routes.py` (probe failure, precheck duplicate, in-batch duplicate, both resolved-URL-collision cases) with a `retailer` assertion each, covering both the raw-hostname-derivation path and the already-resolved `result.retailer` reuse path.
- [x] Full backend suite: **338 passed** (313 + 21 + 4, the 5 `ListingFailure` cases were assertion additions to existing tests, not new ones). Frontend `tsc --noEmit`: clean.
- [ ] **Manual (you):** add a product with a blank name, a non-`RETAILER_MAP` URL — confirm both `Product.name` and the retailer badge fill in after the first scrape completes, without blocking the add response.
- [ ] **Manual (you):** add a product with a blank name via an Amazon URL — confirm `Product.name` still fills in (via `AmazonCAScraper`'s own `#productTitle` extraction) even though the retailer badge stays statically "Amazon".
- [ ] **Manual (you):** manually edit a listing's `retailer` via the sheet, wait for the next scrape (or trigger `POST /api/poll/prices`), confirm the manual edit survives (not stomped by re-inference).
- [ ] **Manual (you):** bulk-add several URLs including at least one duplicate/unscrapable, confirm the failure toast shows retailer names, not raw URLs.

## Cleanup
- [x] No leftover unused imports after the `_find_jsonld_product`/`_find_jsonld_type` refactor — `_find_jsonld_product` kept as a thin wrapper, all existing call sites unchanged.
- [x] Full backend suite + `tsc --noEmit` both clean.
