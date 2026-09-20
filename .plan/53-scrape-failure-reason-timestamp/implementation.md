# Issue #53: Implementation

## Steps

### 1. `ScraperResult` + helpers
- [x] Add `error_reason: str | None = None` to `ScraperResult` (`services/scraper/result.py`)
- [x] Add `_describe_exception(exc) -> str` in `base.py` — `"TypeName: first line of message"`, truncated to 200 chars, type name alone when the message is empty (raw `str(exc)` can be empty — `httpx.ConnectError("")`, bare `TimeoutError()` — or a multi-line Playwright call log)
- [x] Add `_detect_bot_block(soup) -> str | None` in `base.py` — page title `"just a moment"` (Cloudflare); title `"access denied"` **and** `edgesuite`/`reference #` in the text (Akamai); `None` otherwise
- [x] In `_run_hierarchy`, when `result is None` (the formerly silent-error path), set `error_reason` to the detected reason, else `"no price found on page"`

### 2. Populate `error_reason` at every error-return site
- [x] `http_scraper.py`'s `except Exception:` — `error_reason=_describe_exception(exc)`
- [x] `patchright_scraper.py`'s `PatchrightScraper.get_price`'s `except Exception:` — `error_reason=_describe_exception(exc)`
- [x] `patchright_scraper.py`'s `AmazonCAScraper.get_price`'s browser-launch-failure `except Exception:` — `error_reason=_describe_exception(exc)`
- [x] `patchright_scraper.py`'s `AmazonCAScraper.get_price`'s retry-exhaustion return — `error_reason="exhausted retries"`
- [x] `ikea_scraper.py` (built under #54, missed by the first draft of this plan) — three error returns: no item number → `"no item number found in URL"`; missing hydrate payload → `"availability data missing from IKEA response"`; generic `except Exception:` → `_describe_exception(exc)`

### 3. Database — migration + model
- [x] New Alembic migration `0017_listing_failure_and_checked_at.py` — `last_scrape_error` (String), `last_checked_at` (DateTime(timezone=True)), both nullable, no backfill. (`last_failed_at` was in the first draft and dropped — see `context.md` decision 7.)
- [x] Add the two fields to `Listing` (`models/watch_item.py`)

### 4. `jobs.py` — wire the new fields through `process_item`
- [x] Two small helpers so no path can set `"error"` without a reason: `_record_failure(listing, reason, now)` (sets `last_scrape_status = "error"`, `last_scrape_error`, `last_checked_at`) and `_clear_failure(listing)` (clears `last_scrape_error`)
- [x] `"oos"` branch: set `last_checked_at`; `_clear_failure` (recovering from a prior error)
- [x] `"error"` branch: `_record_failure(listing, scrape.error_reason or "unknown scraper error", now)` (guarantees non-empty even if a scraper forgets to set one)
- [x] `"ok"` branch: set `last_checked_at`; `_clear_failure` (already clears `restock_at` — same block)
- [x] `"ok"` + `price is None` — change from a bare warning-and-return to `_record_failure(listing, "scraper returned ok status but no price was found", now)` + commit (mirrors the `"error"` branch)
- [x] `_bounded_process_item`'s backstop (sets `"error"` when `process_item` raises unexpectedly for a still-never-scraped listing) — `_record_failure(listing, _describe_exception(exc), now)`; a fourth place that sets `"error"`, missed by the first draft of this plan. Existing guard (`last_scrape_status is None`) kept so it never stomps a status `process_item` already committed

### 5. API surface
- [x] `schemas/listing.py`'s `ListingResponse` — add `last_scrape_error`
- [x] `items.py`'s `_build_listing_response` — pass it through from the ORM `listing`
- [x] `items.py`'s `_fetch_last_checked_map` — swap the `PriceHistory` aggregation for `select(Listing.id, Listing.last_checked_at)` — **kept the function and its call sites**; same `(id, datetime)` row shape. ~8 route tests mock the `db.execute` call sequence including this query's rows, so removing the call would break them for no functional gain
- [x] `compute_last_checked` (`product_status.py`) works unchanged against the new source (it just takes per-listing timestamps); docstring updated for the new "last attempt" meaning

### 6. Frontend — types
- [x] `lib/api/items.ts`'s `Listing` interface — add `last_scrape_error: string | null`

### 7. Frontend — "Failed" badge tooltip (table row + sheet header)
- [x] `describeFailure(listing)` — `last_scrape_error || "no details recorded yet"` (reason only; when it was tried is the Last checked column's job)
- [x] `failedReasonLines` next to `oosRestockLines` in `watchlist/page.tsx` — one line per listing with `last_scrape_status === "error"` (no retailer prefix, matching the OOS tooltip — same known limitation for multi-retailer products, see `challenges.md`)
- [x] `tooltipLinesFor(status)` picks `oosRestockLines` / `failedReasonLines` / none, replacing the two OOS-only badge blocks (table row + sheet header) with one shared pattern
- [x] Null handling: listings already in `"error"` at deploy time have `last_scrape_error = null` until their next scrape — the placeholder covers both the badge tooltip and step 8's icon tooltip

### 8. Frontend — sheet panel per-listing error icon
- [x] Import `CircleAlert` from `lucide-react`
- [x] In the per-listing "Retailers" row, next to the `ExternalLink` icon, render a `CircleAlert` (styled `--status-error`, sized to match its neighbors) when `listing.last_scrape_status === "error"`
- [x] Wrap it in `Tooltip`/`TooltipTrigger` showing that single listing's `describeFailure(listing)` — no aggregation needed, it's already scoped to one listing

### 9. Testing & Validation
- [x] Backend: bot-block detector in `test_base.py` — Cloudflare title, Akamai title + markers (real captured page), "Access Denied" without Akamai markers → generic, missing title
- [x] Backend: `_describe_exception` — empty message → type name only; multi-line → first line only; long → truncated to 200 chars
- [x] Backend: `IKEAScraper` reasons — no item number, missing hydrate payload, exception
- [x] Backend: `test_jobs.py` — reason persisted and `last_checked_at` set on `"error"`; `error_reason` fallback to `"unknown scraper error"`; `last_scrape_error` cleared and `last_checked_at` set on next `"ok"`/`"oos"`; the `ok`+no-price → `error` transition; `_bounded_process_item` backstop persists a reason and leaves an already-committed status alone
- [x] Backend: `test_items_routes.py` — `_listing` fixture gains the new field; response exposes `last_scrape_error`
- [x] Backend: updated the existing tests that asserted full `ScraperResult(price=None, status="error", ...)` equality (`test_ikea` ×5, `test_patchright` ×3, `test_base` ×2) to assert the reason explicitly
- [x] Frontend: `npx tsc --noEmit` and `next lint` after each round of edits
- [ ] Frontend: no unit-test runner exists (#29 is open) — verify the null-placeholder case manually against a `"error"` listing with no reason
- [ ] Manual, real pipeline: serve a fake Akamai deny page locally, point a local listing's URL at it, hit the per-item rescrape button — confirm the Akamai reason appears in both tooltips and on the icon, and Last checked shows "just now"
- [ ] Manual: a genuinely generic failure (no bot-block match) shows `"no price found on page"`, not a blank/broken tooltip
- [ ] Manual: a listing that recovers (`ok`/`oos`) loses its icon and its Failed tooltip

### 10. Deploy
- [ ] Local: `alembic downgrade -1` on the **old** container first (it has the 3-column draft of `0017` baked in), then rebuild, then `alembic upgrade head`
- [ ] Commit, push, then on the Pi: `git pull`, rebuild **both** containers, `alembic upgrade head` (same sequence as `0016`'s deploy)

### 11. Cleanup
- [ ] Remove any debug prints/logs added during testing
- [ ] Update `.doc/issues.md` Issue #53 — mark `[x]` and check off acceptance criteria once verified live
