# #41: Implementation

## Steps

### 1. Extract `spawn()` into a shared module
- [x] Create `backend/app/core/background_tasks.py` with `spawn(coro)` and its `_background_tasks: set[asyncio.Task[None]]` registry, moved verbatim from `trading_agents.py`
- [x] Update `trading_agents.py` to `from app.core.background_tasks import spawn` instead of defining it locally — dropped now-unused `Coroutine`/`Any` imports as a side effect
- [x] Confirm existing TradingAgents tests still pass — moved the one test reaching into `_background_tasks` internals to `tests/core/test_background_tasks.py` (module changed, so its target had to); all 15 pass

### 2. Make `_process_item` callable from `items.py`
- [x] Rename `jobs.py`'s `_process_item` to `process_item`, update `poll_prices`'s call site to match — also renamed 14 `test_process_item_*` tests + their `patch("app.scheduler.jobs._process_item")` targets in `test_jobs.py` (only other place the old name was referenced)
- [x] Confirmed signature (`item_id: int, router: RetailerRouter, queue: asyncio.Queue`) needs no changes — own `AsyncSessionLocal()` per call (no shared session across concurrent invocations); `RetailerRouter` verified stateless (no `__init__`, constructs a fresh scraper instance per call already); `queue` is `app.state.event_queue` (alert path only — confirmed distinct from `sse.py`'s separate module-global broadcast, which needs no parameter)

### 3. Wire background dispatch into `create_item`/`create_listing`
- [x] Added `request: Request` to both route handlers — placed **first** in the signature (matching `poll.py`'s established convention), not between `body`/`db` as originally drafted; the original mid-signature placement broke every existing test in `test_items_routes.py` that calls these handlers positionally (`items.create_item(body, db)`) — fixed by moving `request` first and updating all 13 call sites, same fix `poll.py` already models
- [x] Added `_FIRST_SCRAPE_CONCURRENCY = 3` + `_first_scrape_semaphore = asyncio.Semaphore(3)`, module-level in `items.py`, deliberately separate from `_PROBE_CONCURRENCY` per the Challenges reasoning
- [x] `_bounded_process_item(listing_id, semaphore, queue)` wrapper added — `async with semaphore: await process_item(listing_id, RetailerRouter(), queue)`, fresh `RetailerRouter()` per call
- [x] Wired into `create_item` (loop over `product.listings` after `db.commit()`) and `create_listing` (single listing) — both via `spawn(_bounded_process_item(...))`, not awaited
- [x] Tests: added `_stub_first_scrape_dispatch` autouse fixture (patches `_bounded_process_item` so route-behavior tests don't trigger real scrapes) and 3 new tests asserting the dispatch itself — correct listing IDs, correct semaphore/queue identity, no dispatch for failed/unprobed URLs. Full backend suite: 281 passed (incl. `-W error::RuntimeWarning`, confirming no unawaited-coroutine leak from the `spawn()` wiring)

### 4. `compute_status()` gains "processing"
- [x] Added `"processing"` to `ProductStatus` (`product_status.py`), inserted the check between "all inactive → paused" and "any errored → failed" exactly as planned
- [x] Confirmed priority via 5 new tests: `processing` outranks `failed` (a never-scraped sibling isn't masked by another listing's past error) and `triggered` (a fresh listing added to an already-triggered product reads as processing until it reports); `paused` still outranks `processing`; inactive never-scraped listings don't count (same `active_listings`-only scoping as the existing `failed` check)
- [x] **Found and fixed a real drift bug, not anticipated in the plan:** `schemas/product.py`'s `ProductResponse.status` had its own hand-duplicated `Literal["watching", "triggered", "paused", "failed"]` instead of referencing `product_status.ProductStatus` — adding `"processing"` to one but not the other broke Pydantic validation on every route returning a product with any never-scraped listing (9 of `test_items_routes.py`'s tests, since several fixtures leave `last_scrape_status` at its `None` default). Fixed properly: `schemas/product.py` now imports and uses `ProductStatus` directly instead of a second copy, closing off this exact class of bug for any future status value
- [x] One additional fixture fix: `test_list_items_returns_products_with_computed_fields` asserted `"watching"` but its `_listing()` call never set `last_scrape_status`, defaulting to `None` — correctly surfaced as `"processing"` now; fixed by adding `last_scrape_status="ok"` to match the test's actual intent
- [x] Full backend suite: 286 passed

### 5. Frontend: type + UI states
- [x] Add `"processing"` to `WatchStatus` (`frontend/src/lib/api/items.ts`)
- [x] Add a `STATUS_BADGE["processing"]` entry (`watchlist/page.tsx`) — label "Processing", pick a `Badge` variant distinct from the existing four (likely `"outline"` or a new muted treatment, not `"destructive"`/`"default"` which read as failed/triggered)
- [x] `ProductRow`'s Best Price cell: renders `lucide-react`'s `LoaderCircle` (`animate-spin`, per your preference — no existing spinner primitive was reused) when `product.status === "processing"`, else the existing `best !== null ? ... : "—"` ternary unchanged
- [x] Last Checked and Price History (sparkline) cells: empty string / sparkline suppressed entirely when `product.status === "processing"` — bypasses `formatLastChecked` rather than feeding it `null`, so it stays visually distinct from that function's own `—` (no value came back) rather than collapsing to the same output
- [x] Sheet panel's `Switch`: added `disabled={product.status === "processing"}`
- [x] `tsc --noEmit` and `eslint` both clean on `watchlist/page.tsx`; no existing automated test suite for this page — live verification is step 6, per your usual workflow

### 6. Testing & Validation
- [x] Single real add (e.g. a Shopify URL) — confirm background scrape fires, `PriceHistory` written, SSE push updates the row from "Processing" to real values, verified live. Verified: `muddygeorge.com` add → `watch_items.last_price=52`/`last_scrape_status="ok"`, `price_history` row written, UI flipped "Processing" → "Watching" ($52 > $50 target, correctly not alert-worthy) with no manual refresh
- [ ] Bulk add with 3+ URLs, at least 2 needing Patchright (e.g. multiple `amazon.ca` listings) — confirm all get their own background scrape, genuinely concurrent (check timestamps/logs, not just "all eventually complete" which sequential execution would also satisfy)
- [ ] Confirm concurrent heavy-scrape behavior against Patchright's shared browser context live — this is new territory even after `#40`'s own concurrent-launch verification, since that tested concurrent *launches*, not concurrent *scrapes* against an already-running context
- [x] A deliberately bad/unscrapable URL in the mix — confirm it lands as `last_scrape_status: "error"` without blocking the product/other listings' creation or their own scrapes. Verified: dead `amazon.ca/dp/B000000000` → `"error"`, sibling good listings (`amazon.ca` AirPods, `muddygeorge.com`) both → `"ok"`, nothing blocked
- [x] An alert-crossing add (target price already below a real live price) — confirm Pushover fires from the background scrape path, same as a normal scheduled cycle. Verified: `amazon.ca` AirPods Max listing → `PRICE_DROP` event written, `status="processed"` (dispatcher's `notify.handle()` completed without raising)
- [ ] "Processing" UI verified live: badge, spinner, empty cells, disabled switch — for both single-add and bulk-add
