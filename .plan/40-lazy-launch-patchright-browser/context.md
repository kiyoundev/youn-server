# #40: Context

## Issue Description

`PatchrightScraper.start_browser()`/`close_browser()` (`backend/app/services/scraper/patchright_scraper.py`) are fully implemented but never called anywhere in the running app — confirmed via a full-codebase grep, the only call site is a standalone `smoke_test.py` script. Any code path needing the browser (`detect_scraper_type`'s fallback probe, `AmazonCAScraper`'s actual scraping, `RetailerRouter`'s generic-hierarchy-failed fallback) instantly returns `status="error"` instead of actually trying.

Fix: launch the browser **lazily**, on first real use, guarded by an `asyncio.Lock` — not eagerly at app startup. Originally planned as eager (matching `FinnhubClient`'s unconditional-at-startup pattern); reconsidered after mapping the actual routing flow (`.doc/diagrams/scraper-routing-flow.html`) made it concrete that Patchright is a *minority* path — only `RETAILER_MAP`-mapped retailers (currently just `amazon.ca`) or listings cached as `scraper_type: "patchright"` ever reach it. Most sites never touch it at all.

Full acceptance criteria: see `.doc/issues.md` → Issue #40.

## Component / Route Summary

### Current State
- `PatchrightScraper._context` is always `None` in the running app — `start_browser()` is never invoked outside `smoke_test.py`.
- `RetailerRouter.get_price()` and `detect_scraper_type()` (`router.py`) both call into `PatchrightScraper.get_price()`, which currently short-circuits to `ScraperResult(price=None, status="error")` immediately since `_context is None`.
- This affects the scheduled `poll_prices` job (`jobs.py`, every 6h) for every `amazon.ca` listing and any listing whose `scraper_type` resolved to `"patchright"` — confirmed live this session as the likely cause of the recurring `scraper error for listing 13 (amazon_ca)` log line seen on every Pi restart.
- Confirmed live (this session): manually calling `start_browser()` then `AmazonCAScraper().get_price(...)` against a real product page returns a correct real price — the scraper logic itself works, this is purely a missing wire-up.
- Also confirmed live (this session): `CHROMIUM_PATH`, written to `/etc/environment` by the Dockerfile, is **never actually read** by the running app process (`docker compose exec`'s own shell and the real PID 1 `uvicorn` process both show it unset) — `/etc/environment` is loaded by login shells, not by a container's `CMD`-launched process. This is currently dead code, but harmless: Patchright's own default binary discovery finds Chromium correctly regardless (verified live, same test URL succeeded with `CHROMIUM_PATH` unset).

### Target State
- `PatchrightScraper` gains a class-level `_start_lock: asyncio.Lock`.
- `start_browser()` uses double-checked locking: return immediately if `_context is not None`; otherwise acquire `_start_lock`, re-check, launch only if still unset.
- `get_price()` calls `start_browser()` defensively at its top (or equivalent — ensures the browser exists before use, regardless of caller).
- `close_browser()` remains called from `main.py`'s `lifespan` shutdown (cleanup stays eager even though startup doesn't).
- A new `PatchrightScraper._active_scrapes: int` counter tracks in-flight scrapes (incremented before `new_page()`, decremented in the existing `finally` block).
- A new `PatchrightScraper.recycle_browser()` classmethod, also using `_start_lock` (see Challenges — resolves a launch/recycle race), closes and relaunches the browser context daily when idle.
- A new daily `AsyncIOScheduler` job in `main.py`'s `lifespan`, alongside the existing `poll_prices` registration.
- `.doc/architecture.md`'s Polling Schedule table gains a row for the new job.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/patchright_scraper.py`** — add `_start_lock`, guard `start_browser()`, add `_active_scrapes` counter, add `recycle_browser()`.
- **`backend/app/main.py`** — register the new daily recycle job in `lifespan` (alongside `poll_prices`'s existing `scheduler.add_job(...)` call); `close_browser()`'s shutdown call already fits the existing shutdown block once added.
- **`.doc/architecture.md`** — add the recycle job to the Polling Schedule table.

### Dependencies
- **`app/services/scraper/router.py`** — `RetailerRouter.get_price()` and `detect_scraper_type()` both call through to `PatchrightScraper.get_price()`, which will now trigger the lazy launch on genuine first use.
- **`app/scheduler/jobs.py`** — `poll_prices`'s 6h cycle is the primary real-world caller that triggers first-use launch in steady state (via any `amazon.ca` or cached-`"patchright"` listing).

### New Dependencies
None — uses `asyncio.Lock`, already part of the standard library; no new packages.

### Breaking Changes
None — internal-only change to `PatchrightScraper`'s lifecycle. No API contract, request/response shape, or DB schema changes.
