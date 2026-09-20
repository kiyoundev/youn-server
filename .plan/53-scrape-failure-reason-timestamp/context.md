# Issue #53: Context

## Issue Description

Today a failed listing only ever shows as the single word "failed" (`compute_status`, `product_status.py`) — no retailer-specific reason, no timestamp. Diagnosing the Crate & Barrel case (#52, this session) required a live SSH-into-Pi-and-grep-logs session, plus a temporary code patch to dump raw HTML, because none of this information is persisted anywhere.

Separately, while live-testing #54's IKEA out-of-stock fix, a related gap surfaced: a manual re-poll of an OOS listing correctly updated its price/status/restock date, but the product's displayed "last checked" time stayed stale — because it's derived from `PriceHistory.checked_at`, and `PriceHistory` rows are only ever written on the `"ok"` path. Folded into this issue since it's the same underlying problem (a listing's true "was this checked" state isn't reliably persisted) and shares the same migration.

**Full acceptance criteria** — see `.doc/issues.md` Issue #53 for the verbatim list; summarized in `_index.md`'s Success Criteria above.

**Design decisions resolved via `/grill-me`, this session** (see conversation for full reasoning):
1. `status="ok"` + `price is None` now transitions to `"error"` with its own reason — was previously an ambiguous silent no-op, decided to close that gap along with the others.
2. Error text threads through a new `ScraperResult.error_reason: str | None` field, mirroring how `restock_at` was added this session for IKEA — no new architecture, one more optional field on the existing result object.
3. The Cloudflare-vs-Akamai distinction is detected by **page content** (title/text signatures), not by threading a flag from `patchright_scraper.py`'s Cloudflare-specific wait logic — a flag-based approach would have missed #52's actual real case (Akamai's "Access Denied", not a Cloudflare "Just a moment" challenge).
4. `last_scrape_error` clears on the listing's next `"ok"` **or** `"oos"` scrape, not just `"ok"` — both are legitimate non-broken results.
5. No migration backfill for `last_checked_at` — accept a temporary blank state for existing listings, self-heals within one `poll_prices` cycle (≤6h).
6. UI treatment differs by surface: watchlist table row keeps the existing badge-tooltip pattern (matches the shipped OOS tooltip); the sheet panel instead gets a small `CircleAlert` icon inline on each listing's own row (next to the external-link icon), not a separate "Error section" block. Both tooltips show the **reason only**.
7. **Reversed mid-build:** `last_checked_at` is set on **every poll attempt** (`ok`, `oos` and `error`), not success-only. The first draft made a failed attempt *not* count, plus a separate `last_failed_at`, so a failing listing would read stale. Reversed because "last checked" literally means when we last tried, a failure is already loud (Failed badge + persisted reason), and a listing that stops being polled at all still goes stale. `last_failed_at` then always equalled `last_checked_at` while failed (and cleared on recovery), so it was dropped before shipping. The last *successful* price time is still in `PriceHistory`.

## Component / Route Summary

### Current State

**Backend:**
- `ScraperResult` (`services/scraper/result.py`) has no error-message field — `jobs.py` only ever sees `price`/`status`, never the original exception each scraper already catches and logs (`exc_info=True`) but discards.
- `jobs.py`'s `process_item()` (`scheduler/jobs.py:177-210`):
  - `"oos"` branch (lines 180-194): sets `last_scrape_status`, `restock_at`, conditionally `last_price` — this session's work, already shipped.
  - `"error"` branch (lines 196-200): sets `last_scrape_status = "error"` only, nothing else.
  - `"ok"` + `price is None` (lines 202+): logs a warning, returns without touching `last_scrape_status` at all — silently stale.
- `base.py`'s `_run_hierarchy` returns `ScraperResult(price=None, status="error")` completely silently (no log, no exception) when the page loads but no extraction method finds a price — confirmed via #52 as the actual root cause of an Akamai bot-block going undiagnosed.
- `HTTPScraper`/`PatchrightScraper`/`AmazonCAScraper` each catch real exceptions with `exc_info=True` logging before returning `status="error"` — the message exists in logs, just isn't persisted.
- `Listing` model (`models/watch_item.py`): `id, url, retailer, last_price, last_scrape_status, scraper_type, restock_at, created_at, product_id` — no error/failure/checked-at fields.
- `last_checked` (product-level) is derived entirely from `MAX(PriceHistory.checked_at)` per listing (`items.py:177-182`, `_fetch_last_checked_map`) — `PriceHistory` is only written on `"ok"`.

**Frontend:**
- `watchlist/page.tsx` has `STATUS_BADGE` (badge label/variant map), `draftStatus()` (mirrors backend's `compute_status()` priority for the sheet's draft-toggle preview), and — shipped this session — a `Tooltip` (`components/ui/tooltip.tsx`, Base UI-backed) wired onto the "Out of Stock" badge on both the table row and sheet header, showing `oosRestockLines` (one line per OOS listing).
- The per-listing "Retailers" row in the sheet panel currently shows only retailer name, external-link icon, price, edit/remove buttons — no error indicator at all.

### Target State

- `ScraperResult` gains `error_reason: str | None`.
- Every `status="error"` return site populates it (network/timeout/launch-failure paths use the caught exception; Amazon retry exhaustion uses a fixed string; the previously-silent no-price-found path gets a content-detected reason).
- `status="ok"` + `price is None` becomes a real `"error"` transition with its own reason.
- `Listing` gains `last_scrape_error` and `last_checked_at` — migration `0017`.
- `jobs.py` writes these consistently: clears `last_scrape_error` on `"ok"`/`"oos"`, sets `last_checked_at` on every poll (including `"error"`).
- `_fetch_last_checked_map` reads `last_checked_at` directly instead of aggregating `PriceHistory`.
- `ListingResponse` schema exposes the new fields.
- Frontend: `failedReasonLines` (mirrors `oosRestockLines`) feeds a tooltip on the "Failed" badge (table row + sheet header). Sheet panel's per-listing row gets a `CircleAlert` icon + tooltip when that specific listing is `"error"`.

## Impact & Risk

### Files Changed
- **`backend/app/services/scraper/result.py`** — add `error_reason` field
- **`backend/app/services/scraper/base.py`** — content-based bot-block detector; thread `error_reason` through `_run_hierarchy`'s error return
- **`backend/app/services/scraper/http_scraper.py`**, **`patchright_scraper.py`** — populate `error_reason` at each existing `except Exception:` site and the Amazon retry-exhaustion site
- **`backend/app/services/scraper/ikea_scraper.py`** — populate `error_reason` at its three error returns (built under #54)
- **`backend/app/services/scraper/base.py`** (also) — `_describe_exception` helper so persisted reasons are never empty or multi-line
- **`backend/app/models/watch_item.py`** — two new nullable columns
- **`backend/alembic/versions/0017_listing_failure_and_checked_at.py`** — new migration
- **`backend/app/scheduler/jobs.py`** — populate/clear new fields across all three branches (`ok`/`oos`/`error`), plus the new `ok`+`None`-price → `error` transition, and the `_bounded_process_item` unexpected-exception backstop (a fourth place that sets `"error"`)
- **`backend/app/schemas/listing.py`** — expose new fields on `ListingResponse`
- **`backend/app/api/items.py`** — `_build_listing_response`, `_fetch_last_checked_map` (switch source to `last_checked_at`)
- **`frontend/src/lib/api/items.ts`** — `Listing` interface gains `last_scrape_error`
- **`frontend/src/app/watchlist/page.tsx`** — `failedReasonLines`, badge tooltip wiring, per-listing `CircleAlert` icon + tooltip

### Dependencies
- **`components/ui/tooltip.tsx`** — reused as-is, already ships this session; no new frontend dependency
- **`lucide-react`**`CircleAlert`** — already an installed dependency (icon library already in use throughout this file)

### Breaking Changes
None — all new columns are nullable additions, `ScraperResult.error_reason` and `restock_at`-style fields default to `None`, existing callers unaffected. The one behavioral change (`ok`+`None`-price now becomes visibly `"error"` instead of silently stale) is the intended fix, not incidental breakage — see `challenges.md` for what it means in practice.
