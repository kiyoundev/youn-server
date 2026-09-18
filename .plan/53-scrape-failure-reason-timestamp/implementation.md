# Issue #53: Implementation

## Steps

### 1. `ScraperResult` + content-based bot-block detector
- [ ] Add `error_reason: str | None = None` to `ScraperResult` (`services/scraper/result.py`)
- [ ] Add a small helper in `base.py`, e.g. `_detect_bot_block(html: str) -> str | None` — checks page title/text for `"Just a moment"` (Cloudflare) and `"Access Denied"` + an edgesuite/reference-number pattern (Akamai); returns `None` if neither matches
- [ ] In `_run_hierarchy`, when `result is None` (the existing silent-error path), call the detector and set `error_reason` on the returned `ScraperResult(status="error", ...)` — detected reason if matched, else `"no price found on page"`

### 2. Populate `error_reason` at every existing error-return site
- [ ] `http_scraper.py`'s `except Exception:` — `error_reason=str(exc)`
- [ ] `patchright_scraper.py`'s `PatchrightScraper.get_price`'s `except Exception:` — `error_reason=str(exc)`
- [ ] `patchright_scraper.py`'s `AmazonCAScraper.get_price`'s browser-launch-failure `except Exception:` — `error_reason=str(exc)`
- [ ] `patchright_scraper.py`'s `AmazonCAScraper.get_price`'s retry-exhaustion return — `error_reason="exhausted retries"`

### 3. Database — migration + model
- [ ] New Alembic migration `0017_listing_failure_and_checked_at.py` — `last_scrape_error` (String), `last_failed_at` (DateTime(timezone=True)), `last_checked_at` (DateTime(timezone=True)), all nullable, no backfill
- [ ] Add the three fields to `Listing` (`models/watch_item.py`)

### 4. `jobs.py` — wire the new fields through `process_item`
- [ ] `"oos"` branch: set `last_checked_at = datetime.now(timezone.utc)`; clear `last_scrape_error`/`last_failed_at` to `None` (recovering from a prior error)
- [ ] `"error"` branch: set `last_scrape_error = scrape.error_reason`, `last_failed_at = datetime.now(timezone.utc)`
- [ ] `"ok"` branch: set `last_checked_at = datetime.now(timezone.utc)`; clear `last_scrape_error`/`last_failed_at` to `None` (already clears `restock_at` this session — same block)
- [ ] New: `"ok"` + `price is None` — change from a bare warning-and-return to setting `last_scrape_status = "error"`, `last_scrape_error = "scraper returned ok status but no price was found"`, `last_failed_at = now`, then commit (mirrors the existing `"error"` branch's shape)

### 5. API surface
- [ ] `schemas/listing.py`'s `ListingResponse` — add `last_scrape_error`, `last_failed_at`
- [ ] `items.py`'s `_build_listing_response` — pass both through from the ORM `listing`
- [ ] `items.py`'s `_fetch_last_checked_map` — replace the `PriceHistory`-aggregation query with a direct read of `Listing.last_checked_at` per listing (no more `PriceHistory` join needed for this specific map — simplifies the query to a plain column select)
- [ ] Confirm `compute_last_checked` (`product_status.py`) still works unchanged against the new source (it just takes a list of per-listing timestamps — source doesn't matter to it)

### 6. Frontend — types
- [ ] `lib/api/items.ts`'s `Listing` interface — add `last_scrape_error: string | null`, `last_failed_at: string | null`

### 7. Frontend — "Failed" badge tooltip (table row + sheet header)
- [ ] Add `failedReasonLines` next to the existing `oosRestockLines` in `watchlist/page.tsx` — one line per listing with `last_scrape_status === "error"`: `` `${l.last_scrape_error} (${relativeTime(l.last_failed_at)})` `` (no retailer prefix, matching the OOS tooltip's established format — same known limitation for multi-retailer products, see `challenges.md`)
- [ ] Wire the same `Tooltip`/`TooltipTrigger render={...}` pattern already used for `"out_of_stock"` onto the `"failed"` case, both the table row badge (`product.status === "failed"`) and the sheet header badge (`draftStatus(...) === "failed"`)
- [ ] Reuse (or extract) a small relative-time formatter — `formatLastChecked` already exists in this file for a similar shape; check whether it's directly reusable for `last_failed_at` or needs a near-identical sibling

### 8. Frontend — sheet panel per-listing error icon
- [ ] Import `CircleAlert` from `lucide-react` in `watchlist/page.tsx`
- [ ] In the per-listing "Retailers" row (next to the existing `ExternalLink` icon/link), conditionally render a `CircleAlert` icon when `listing.last_scrape_status === "error"`, styled with `--status-error`, sized to match the existing `ExternalLink`/`Pencil`/`Trash2` icons in that row
- [ ] Wrap it in `Tooltip`/`TooltipTrigger` (render prop, same pattern) showing that single listing's own `last_scrape_error` + relative `last_failed_at` — no aggregation needed here, it's already scoped to one listing

### 9. Testing & Validation
- [ ] Backend: extend `tests/scraper/test_base.py` (or a new test) for the bot-block detector — Cloudflare title match, Akamai title+pattern match, neither-match fallback
- [ ] Backend: extend `tests/scraper/test_ikea.py`-adjacent or `http_scraper`/`patchright_scraper` tests to assert `error_reason` populated on each error path
- [ ] Backend: extend `tests/scheduler/test_jobs.py` — `error_reason`/`last_failed_at` set on `"error"`; both cleared on next `"ok"`/`"oos"`; `last_checked_at` set on `"ok"`/`"oos"`, untouched on `"error"`; the new `ok`+`None`-price → `error` transition
- [ ] Backend: extend `tests/services/test_product_status.py` if `compute_last_checked`'s contract needs any adjustment (likely none — it's source-agnostic)
- [ ] Backend: extend `tests/api/test_items_routes.py`'s `_listing` fixture factory with the new fields (same fix needed as `restock_at` required this session)
- [ ] Frontend: `npx tsc --noEmit` after each round of edits
- [ ] Manual: re-trigger #52's Crate & Barrel listing (if still reproducible) — confirm the Akamai-specific reason text shows up correctly, not the generic fallback
- [ ] Manual: verify a listing with a genuinely generic failure (no bot-block match) shows `"no price found on page"`, not a blank/broken tooltip

### 10. Deploy
- [ ] Commit, rebuild backend + frontend containers locally, verify
- [ ] Push, `git pull` + rebuild both containers + `alembic upgrade head` on the Pi (same sequence as `0016`'s deploy this session)

### 11. Cleanup
- [ ] Remove any debug prints/logs added during testing
- [ ] Update `.doc/issues.md` Issue #53 — mark `[x]` and check off acceptance criteria once verified live
