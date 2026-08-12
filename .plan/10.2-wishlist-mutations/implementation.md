# Issue #10.2: Implementation

## Steps

### 1. Setup & Configuration
- [x] `cd frontend && npx shadcn@latest add toast` — generated `components/ui/toast.tsx` from the registry (`base-nova` preset). Ships its own `toast` singleton (`createToastManager()`) that `Toaster`'s `toastManager` prop defaults to.
- [x] `frontend/src/lib/toast.ts` — `toast.success()`/`toast.error()` sugar wrapping the registry's own `toast` manager (imported from `@/components/ui/toast`, not a second `createToastManager()` instance — a second instance wouldn't be wired to the mounted `<Toaster/>` and calls would silently go nowhere)
- [x] `<Toaster />` mounted in `frontend/src/app/layout.tsx` (inside `<body>`, alongside `<Nav />`, no props — uses its default internal manager)

### 2. Backend — schema & validator changes

Superseded once — `ProductCreate.url: str | None` (single, optional) was built first, then reworked again into the bulk `urls: list[str]` shape below after further grilling surfaced that a single-request bulk endpoint could safely parallelize the slow part (scraper-type probing) in a way N sequential frontend requests structurally couldn't (see `challenges.md`). What's actually in the codebase now:

- [x] `backend/app/schemas/validators.py` — guard `validate_http_url` against `None` (`if value is None: return value` before `urlparse`) — still needed for `ListingUpdate.url` below, even though `ProductCreate` moved off `url: str | None`
- [x] `backend/app/schemas/product.py` — `ProductCreate.urls: list[str] = []` (replaces the single optional `url`; `retailer`/`scraper_type` override fields dropped, meaningless once there can be multiple URLs), plus new `ListingFailure` and `ProductCreateResponse` schemas
- [x] `backend/app/schemas/listing.py` — `ListingUpdate` gains `url: str | None = None` and `retailer: str | None = None` (unaffected by the bulk-create rework — this is the separate listing-URL-edit capability)
- [x] **Post-hoc addition, found via manual testing:** product `name` wasn't trimmed of leading/trailing whitespace anywhere — frontend fix in step 7/8 (`.trim()` on `createProduct`'s payload and the inline name-edit handler), plus a backend-side `strip_whitespace` validator (`validators.py`, same pattern/reasoning as `validate_http_url` — frontend trim is trivially bypassed by a direct API call) applied to `ProductCreate.name` and `ProductUpdate.name`. 3 new tests in `tests/schemas/test_product_schema.py`. Full suite: 277 passed.

### 3. Backend — route logic
- [x] `create_item` (`backend/app/api/items.py`) — rewritten for the bulk contract: in-batch dedup → single `WHERE url IN (...)` existing-URL check → concurrent probing of survivors via `asyncio.gather` bounded by `asyncio.Semaphore(_PROBE_CONCURRENCY = 3)` (`_resolve_one` wraps `_resolve_retailer_and_scraper_type`, never raises — catches `HTTPException` and returns it as a `_ProbeResult.error` instead, so one bad URL can't cancel sibling probes in the same `gather`) → one commit with product + every successful listing → returns `ProductCreateResponse{product, failed}`
- [x] `update_listing` (`backend/app/api/items.py`) — when `body.url` is provided and differs from `listing.url`: run the duplicate-URL check (excluding the listing's own id), call `_resolve_retailer_and_scraper_type`, apply `url`/`retailer`/`scraper_type`; keep the existing `active` handling unchanged. Unaffected by the bulk-create rework.
- [x] Ran `backend/tests/api/test_items_routes.py` locally at each stage to confirm nothing existing broke
- [x] **Post-hoc fix, found via live UI testing against real Postgres, not caught by the mocked test suite:** `product.listings = []` added right after constructing `product`, before any conditional logic — without it, a request where every URL fails validation (or `urls: []`) never touches `.listings` before commit, and the first access afterward (in `_build_product_response`, unawaited) crashes with `MissingGreenlet`. Full root-cause writeup in `challenges.md` #9.

### 4. Backend — tests

Reworked alongside the bulk redesign — 8 `create_item` tests now (was 4), covering the new partial-success/concurrency contract:

- [x] `POST /api/items` with a known-domain URL → skips the probe (`detect_scraper_type` not awaited)
- [x] `POST /api/items` with an unknown-domain URL → probes, stores the detected `scraper_type`
- [x] Probe failure (unscrapable URL) → **reported in `failed`, not raised** — behavior change from the old single-URL design's `400`; product still created (with fewer/zero listings). This was a deliberate design choice, not a regression — see `challenges.md`.
- [x] Duplicate URL (pre-existing in DB) → **reported in `failed`, not raised** — same behavior-change note as above, was a `409` for the whole request before
- [x] Two identical URLs in one request (in-batch collision) → second one reported in `failed`, first one still creates a listing
- [x] Commit-time race (`IntegrityError`) → still a real `409` for the whole request (the one case that still aborts everything, since it's not attributable to a specific URL)
- [x] `urls: []` (omitted) → product created with zero listings, no DB query fired at all (`db.execute.assert_not_called()`)
- [x] Multiple valid URLs → all probed (`detect_scraper_type` awaited once per URL), all listings created, `failed` empty

Plus the pre-existing `update_listing` URL-change/collision tests, unaffected by this rework. Full suite: **274 passed** (`pytest -q`, whole `backend/`), including regression coverage for every other route this issue didn't touch.

### 5. Frontend — proxy relay
- [x] `frontend/src/app/api/proxy/[...path]/route.ts` — `relay()` helper + `RouteContext` type alias added, `POST`/`PATCH`/`DELETE` exported alongside `GET`; `tsc --noEmit` clean (only pre-existing, unrelated errors elsewhere in the project)
- [x] `DELETE`'s `204` verified: empty `resp.text()` → falsy → `body || null` and `headers: {}`, no `Content-Type` forced onto a bodyless response
- [x] Missing `API_KEY` env var now fails loud: `relay()` short-circuits to a `500` with an explicit "Proxy misconfigured" message before ever calling the backend, instead of silently sending an empty `X-API-Key` and getting back a generic backend `401` indistinguishable from a real bad-credential case (pre-existing gap in the original `GET`-only handler, fixed while touching this file — caught in review, not part of the original grill-me pass)

### 6. Frontend — data layer
- [x] New `frontend/src/lib/api/items.ts` — `ApiError` class + `createProduct`, `createListing`, `updateProduct`, `updateListing`, `deleteProduct`, `deleteListing`, each via a shared `request<T>()` helper; throws `ApiError(status, detail)` on non-2xx, returns parsed JSON otherwise (or `undefined` on `204`). Also exports `Product`/`Listing`/`WatchStatus` (mirrors `page.tsx`'s current local interfaces) — **page.tsx should import these from here in step 7+ rather than keep its own duplicate**, to avoid the two drifting apart. `tsc --noEmit` clean.
- [x] Updated after the bulk-create rework: `createProduct(payload: ProductCreatePayload)` now takes `{name, target_price, urls: string[]}` and returns `Promise<ProductCreateResult>` (`{product: Product, failed: ListingFailure[]}`), not `Promise<Product>` — callers must read `.product` and check `.failed`, not treat the resolved value as the product directly. New exported types: `ListingFailure`, `ProductCreateResult`.

### 7. Frontend — Add Item dialog

**Design history, superseded twice — stated plainly so this doesn't read as three live designs at once:**
1. *Chained*: `createProduct` (1 URL or none) + sequential `createListing` per remaining URL, foreground, dialog blocked for the whole chain.
2. *Chained + background*: same N requests, but dialog closes after the fast `createProduct` call and the `createListing` loop continues in the background with a per-product in-flight counter ("Validating N retailers…" indicator, "Path A"). Built to hide `createListing`'s per-URL `detect_scraper_type` latency without true optimistic UI.
3. **Current, live design**: bulk `POST /api/items` (§2-4 above) — one request, backend probes every URL concurrently (bounded). Total wait ≈ the slowest single probe, not the sum. This is fast enough that design 2's whole reason to exist (hiding a long sequential wait) no longer applies — a plain awaited `Save` with a spinner covers it. **Design 2 is fully removed, not layered on**: no in-flight `Map`, no background continuation function, no per-listing incremental `mutate()`, no `ProductRow` in-flight prop, no "Validating N retailers…" indicator.

- [x] `handleAddItem`: `createProduct({name, target_price, urls: newItemUrlLines})` (awaited, `isSubmitting` disables Save for the duration, button reads "Saving…")
- [x] On success: `mutate('/api/proxy/items')`, close dialog, reset form. One summary toast from the response's `failed` array — `toast.success(...)` if empty, `toast.error(..., {persist: true})` listing which URL(s) failed and why (`failed[i].detail`) otherwise.
- [x] On `createProduct` itself throwing (`ApiError`): `toast.error(e.detail)`, dialog stays open for inline retry.
- [x] `page.tsx`'s local `Product`/`Listing`/`WatchStatus` interfaces replaced with imports from `lib/api/items.ts` (step 6's note). `tsc --noEmit` clean (same 3 pre-existing, unrelated `pill`-variant errors as before, nothing new).
- [x] Worth knowing, not worth building around: since this is now one request, there's no more "user closes the tab mid-chain" partial-listing scenario from design 2 — that failure mode is gone along with the background loop that created it.

### 8. Frontend — sheet inline edits
- [x] Name edit (Enter key) → `updateProduct(id, {name})` → `mutate` → toast. Guards: skip if empty after trim, skip if unchanged (no round-trip for a no-op Enter press).
- [x] Target price edit (Enter key) → `updateProduct(id, {target_price})` → `mutate` → toast. Guards: skip if not `> 0`, skip if unchanged.
- [x] Listing URL edit (Enter key, existing `isValidUrl` gate stays as the pre-flight check) → `updateListing(productId, listingId, {url})` → `mutate` → toast; on `409` specifically, toast `"That URL is already being watched"` instead of the generic failure message. Guard: skip if unchanged.
- [x] Add-listing draft (Enter key) → `createListing(productId, {url})` → `mutate` → toast
- [x] Remove-listing (trash icon) → `deleteListing(productId, listingId)` → `mutate` → toast. Revised from the original `disabled` guard: the icon is no longer rendered at all when it's the product's only listing, rather than shown greyed-out — avoids "why is this disabled" ambiguity for a single-retailer product.

All 5 use the same async/await + try/catch shape as `handleAddItem` (step 7) for consistency. `tsc --noEmit` clean (same 3 pre-existing, unrelated `pill`-variant errors, nothing new).

### 9. Frontend — pause/resume (new UI)

**Revised after building it once — moved from per-listing to product-level.** Built per-listing first (one `Switch` per retailer row), then reconsidered: most users think "pause this item," not "pause this specific retailer's listing," and per-listing toggles reopened the exact ambiguity grilling avoided earlier (row-level bulk vs. individually-paused listings) the moment a product-level control got added alongside them. Resolved by **replacing**, not adding to, the per-listing switches — removes the ambiguity entirely, since there's no per-listing toggle left to conflict with.

- [x] `npx shadcn@latest add switch` — generated `components/ui/switch.tsx` (`base-nova` preset, Base UI `Switch.Root`/`Switch.Thumb`, `checked`/`onCheckedChange` props).
- [x] One `Switch` in the sheet's Status row, next to the existing (unchanged) status `Badge`. `checked={product.status !== "paused"}`.
- [x] On toggle → bulk-`updateListing({active})` across every one of `product.listings` via `Promise.allSettled` (parallel — no duplicate-URL race risk here, unlike the add-flow's URL-creation race, since this only ever touches the `active` flag) → `mutate` once → one toast, reporting a partial-failure count (`{persist: true}`) if any listing's PATCH failed, success (`"Paused"`/`"Resumed"`) otherwise.
- [x] No product-level `active` field was added to the backend — this still works by bulk-toggling every listing's real `active` column, same mechanism `compute_status` already derives `"paused"` from. No backend change needed for this step.

`tsc --noEmit` clean (same 3 pre-existing, unrelated `pill`-variant errors, nothing new).

### 10. Frontend — product delete
- [x] Row dropdown "Delete" opens a confirm `Dialog` (`Delete "{name}"? This removes all N listings and their price history.`, Cancel/Delete) instead of calling `console.log` directly. Local `isDeleteDialogOpen` state per `ProductRow` (consistent with the row's other local state, e.g. `historyByListing` — no prop-drilling needed since it's naturally per-product scoped, unlike the single page-level Add Item dialog).
- [x] On confirm → `deleteProduct(id)` → `mutate` → toast; if `openId === id`, reset `openId` to `null` so the sheet closes. Dialog closes in a `finally` regardless of success/failure.

`tsc --noEmit` clean.

### 11. Testing & Validation

> **Side note — dev DB access off home network.** `DATABASE_URL` (root `.env`) points at the NAS's plain LAN IP (`<nas-ip>`), not a Tailscale address — unreachable unless on home wifi or routed onto that LAN some other way (e.g. a Tailscale subnet route advertised by a device already in the tailnet; no Pi deployed yet, so that path doesn't exist currently either). Rather than blocking manual testing on network access, use a disposable local Postgres for this session:
> 1. `brew install postgresql@16 && brew services start postgresql@16 && createdb youn_server_dev` (or a `docker run postgres` container — either works)
> 2. Create `backend/.env` (gitignored, doesn't exist yet) with just `DATABASE_URL=postgresql+asyncpg://...@localhost:5432/youn_server_dev` — `config.py` loads `["../.env", ".env"]` in order, so this overrides *only* the DB target for anything run from `backend/`, root `.env`/the NAS config stays untouched
> 3. `cd backend && .venv/bin/alembic upgrade head` — builds the schema fresh on the empty local DB (same migrations `alembic/env.py` would run against the NAS)
> 4. Start `uvicorn` as normal — now network-independent
> 5. Delete/rename `backend/.env` when back on home network (or done testing) to fall back to the real NAS config, nothing else to undo
>
> Empty local DB, no real watchlist data — fine for verifying this issue's mutation logic works, not a substitute for testing against real data before considering the issue done.

- [ ] Manual: add an item with 3 URLs, one a duplicate of an existing listing → confirm the product + 2 listings persist in one request, toast names the failed URL
- [ ] Manual: edit a listing's URL to one already watched under a different product → confirm `409` toast, no local state change
- [ ] Manual: edit a listing's URL successfully → confirm price history for that listing is still present (chart/sparkline unchanged, not reset)
- [ ] Manual: pause a listing, confirm product status badge flips to "Paused" once it's the last active listing turned off; resume it, confirm badge reflects rollup again
- [ ] Manual: delete a product while its sheet is open → confirm sheet closes, row disappears
- [ ] Manual: confirm `X-API-Key` never appears in the browser Network tab across all of the above (proxy check, same AC `#36` already established)
- [ ] Edge case: submit the Add Item dialog with an empty URL textarea — confirm `canSubmitNewItem`'s existing guard still blocks it (unchanged, but re-verify against the new submit handler)

### 12. Cleanup
- [x] `console.log` stubs — zero remaining in `watchlist/page.tsx` (grep confirms)
- [x] `npm run lint` (frontend) — clean, no warnings or errors
- [x] Backend lint/format step — **doesn't exist to run.** Checked `requirements-dev.txt` (`pytest`, `pytest-asyncio`, `respx`, `paracelsus` only) and `pyproject.toml` (no `[tool.ruff]`/`[tool.black]`/`[tool.mypy]` section at all) — no lint/format tool is configured for this backend, not something specific to this issue. Not silently skipping it; flagging that this checklist item assumed tooling that isn't there. Worth its own small setup task if wanted, separate from `#10.2`.
