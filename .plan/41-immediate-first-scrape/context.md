# #41: Context

## Issue Description

Today, a newly-added product/listing shows `—` for price/status until the next scheduled 6h `poll_prices` cycle, or a manual `POST /api/poll/prices` call. Add a background first-scrape: after `create_item`/`create_listing` returns, fire a background task per newly-created listing that runs the same scrape-write-broadcast logic `_process_item` (`jobs.py`) already does. Deliberately not synchronous (would make "Saving…" hang up to ~30s for a `Patchright`-dependent site).

Also adds a "Processing" UI state — a product's status badge shows "Processing" while any of its listings has never been scraped (`last_scrape_status: null`), with a Best Price spinner and empty (not dash) Last Checked/Price History cells, and the sheet panel's active/inactive `Switch` disabled during that state.

Full acceptance criteria: `.doc/issues.md` → Issue #41.

## Component / Route Summary

### Current State
- `POST /api/items` (`create_item`) and `POST /api/items/{id}/listings` (`create_listing`), both in `backend/app/api/items.py`, create rows and return immediately — nothing scrapes them.
- `_process_item(item_id, router, queue)` in `backend/app/scheduler/jobs.py` already does exactly the scrape-write-broadcast work needed (opens its own DB session, calls `RetailerRouter.get_price()`, writes `PriceHistory`, updates `last_price`/`last_scrape_status`, checks the alert threshold, unconditionally broadcasts via `#36`'s SSE). It's already parameterized per-`item_id`, not coupled to iterating `poll_prices`'s active-listings query beyond that being its only current caller — genuinely reusable as-is, no real extraction work needed on `_process_item` itself.
- `backend/app/services/product_status.py`'s `compute_status()` already rolls up listing state into one of `"watching" | "triggered" | "paused" | "failed"`, priority-ordered. This is the natural, existing extension point for a `"processing"` value — status is already computed server-side from listing state, not client-side.
- `ListingResponse.last_scrape_status` (`backend/app/schemas/listing.py`) is already `Literal["ok", "oos", "error"] | None` — the frontend already receives `null` for a never-scraped listing. No new backend field needed for the "processing" signal.
- `backend/app/services/trading_agents.py` already has a `spawn(coro)` helper (`asyncio.create_task` + a module-level `set` holding strong references + `add_done_callback` auto-discard) solving exactly "fire an independent background coroutine that must survive to completion without being prematurely garbage-collected." Generic, no TradingAgents-specific logic in it.
- `backend/app/api/items.py`'s `_PROBE_CONCURRENCY = 3` / `asyncio.Semaphore` pattern already exists for bulk-add's routing probes (`#10.2`) — same numeric bound this issue reuses, but for a heavier operation (see Challenges).

### Target State
- A new shared module (see "Files Changed" below) hosts `spawn()`, imported by both `trading_agents.py` and the new dispatch code in `items.py` — avoids an awkward cross-import from a TradingAgents-named file, and avoids duplicating the same ~10-line pattern in two places.
- `create_item`/`create_listing` fire one `spawn(_process_item(...))` call per newly-created listing, each internally bounded by a shared `asyncio.Semaphore(3)`, **after** the DB commit and before the response is returned — real concurrency, not FastAPI's sequential `BackgroundTasks`.
- `compute_status()` gains a `"processing"` branch: any active listing with `last_scrape_status is None` → `"processing"`, checked after the existing "all inactive → paused" check but before "any errored → failed" (a listing that's never been scraped hasn't errored yet, and shouldn't read as silently "watching" either).
- `ProductStatus` (backend) and `WatchStatus` (frontend, `frontend/src/lib/api/items.ts`) both gain `"processing"` as a literal value.
- `frontend/src/app/watchlist/page.tsx`: `STATUS_BADGE` gets a `"processing"` entry; Best Price cell renders a spinner, Last Checked/Price History cells render empty string, and the sheet panel's `Switch` gets `disabled` — all gated on the product's `status === "processing"`.

## Impact & Risk

### Files Changed
- **New: `backend/app/core/background_tasks.py`** (or similar neutral name) — `spawn()` + its registry, moved out of `trading_agents.py`.
- **`backend/app/services/trading_agents.py`** — import `spawn` from the new location instead of defining it locally; no behavior change.
- **`backend/app/api/items.py`** — `create_item`/`create_listing` dispatch `spawn(_process_item(...))` per new listing, semaphore-bounded, after commit.
- **`backend/app/scheduler/jobs.py`** — `_process_item` likely needs to become importable (drop leading underscore, or re-export) since it's now called from `items.py` too, not just this module's own `poll_prices`.
- **`backend/app/services/product_status.py`** — `ProductStatus` Literal + `compute_status()` gain the `"processing"` branch.
- **`frontend/src/lib/api/items.ts`** — `WatchStatus` gains `"processing"`.
- **`frontend/src/app/watchlist/page.tsx`** — `STATUS_BADGE` entry, Best Price spinner, empty-string cells, disabled `Switch`.

### Dependencies
- **`app/services/scraper/router.py`'s `RetailerRouter`** — stateless, safe to instantiate fresh per dispatch (unlike `PatchrightScraper`, which is itself a shared classmethod-based singleton underneath — instantiating multiple `RetailerRouter()`s doesn't create multiple browsers).
- **`app.state.event_queue`** — `_process_item` needs the same shared `asyncio.Queue` the scheduler uses (for alert-worthy `Event` writes to reach the dispatcher). `items.py`'s route handlers need a `Request` parameter to reach `request.app.state.event_queue`, which they don't currently take.
- **`#40`'s lock-guarded lazy launch** — this is the first time Patchright's shared browser context gets exercised *concurrently* for the *heavy* scrape path (not `#10.2`'s lighter routing-probe concurrency). Already flagged as needing live verification, not assumed safe by extrapolation.

### New Dependencies
None — reuses `asyncio.Semaphore`/`asyncio.create_task`, already used elsewhere in this codebase.

### Breaking Changes
None to existing behavior — `"processing"` is a new status value, not a change to any existing one. Any frontend/backend code exhaustively switching on `WatchStatus`/`ProductStatus` without a default case would need updating to handle it (only one such site: `STATUS_BADGE`'s `Record<WatchStatus, ...>` — a missing key there is a TypeScript compile error, not a silent runtime gap).
