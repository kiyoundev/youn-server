# #19: Review

## AI Review
<!-- Populated by running `/code-reviewer` before the final commit -->

Run 2026-10-29 on `feature/19-portfolio-holdings-prices-summary` (7 commits, 47 files, ~+4.8k lines). Backend suite 873 pass; `tsc` and `next lint` clean.

**Intent:** replace the mock holdings and summary on `/portfolio` with ledger-derived positions, priced via Finnhub (USD) and yfinance (CAD), with asset type, last-traded date, allocation, invested total, a cache and the UI.

**Verdict:** Request Changes. Fix #1-#3 before relying on the Pi deployment; the rest are minor.

**Status:** all items resolved 2026-10-29 (#1-#5 and #7 fixed, #6, #8, #9 closed as won't fix). Backend suite 880 pass; `tsc` and `next lint` clean.

### Major

#### 1. No timeout on the yfinance price call
- [x] Fixed
- **File:** `services/prices.py` (`_fetch`)
- **Verified:** script. `get_price` was still waiting after 2s with a hung fake Yahoo.
- **Problem:** a hang holds the per-key lock and every `/positions` and `/summary` request waiting on it. The other upstreams are bounded (`AssetTypeService` 5s, Finnhub client 10s).
- **Fix:** wrap the executor call in `asyncio.wait_for` (~5s) and treat a timeout as a failure (stale / unavailable). Add a test with a blocking fake, like the one in `test_asset_types.py`.
- **Done:** `_YFINANCE_TIMEOUT_SECONDS = 5` around the executor call in `_fetch`; three tests in `test_prices.py` (hung call is a failure; concurrent callers get one stale result and one attempt, then recovery; cold start is unavailable). Mutation-checked: without `wait_for` all three fail. `.doc/diagrams/price-cache-lock-sequence.html` updated.
- **Caveat:** `wait_for` stops waiting but cannot kill the executor thread, which runs on until yfinance gives up. While Yahoo hangs, each 30s tick leaves one thread per CAD symbol; the default executor has roughly 8 threads on the Pi. How long a real yfinance call can hang was not checked.

#### 2. DB transaction held across slow upstream calls
- [x] Fixed
- **File:** `api/positions.py` (`_load_priced_rows`), `core/db.py` (`get_db`)
- **Verified:** traced from code; pool exhaustion not reproduced.
- **Problem:** `_load_usd_rate` / the ledger load autobegin a transaction before `prices.get_prices` / `types.get_types`, so a pooled connection sits idle-in-transaction while waiting. Combined with #1, 30s polls could exhaust the pool (5 + 10 overflow) and stall other routes.
- **Fix:** `await db.rollback()` once the ledger and FX reads are done, before the upstream awaits.
- **Done:** `_load_priced_rows` rolls back right after the two reads. New test `test_the_db_transaction_ends_before_any_upstream_call` checks the order (FX get, rollback, then prices and types); mutation-checked with the rollback removed and with it moved after the upstream calls. The test uses fakes, so it shows call order, not that a real connection returns to the pool; that rests on SQLAlchemy's documented `rollback()` behaviour.

#### 3. Finnhub token written to logs (security)
- [x] Fixed
- **File:** `services/stocks.py` (`FinnhubClient.get_price`)
- **Verified:** script. The `httpx.HTTPStatusError` message contains the full URL, `token=...` included.
- **Problem:** the token is sent as a query param and failures are logged with `exc_info=True`. Pre-existing, but #19 calls it every 15s per USD holding, so a 429 or outage would write the key to Docker logs repeatedly.
- **Fix:** send it as the `X-Finnhub-Token` header, or log without the exception message / URL.
- **Done:** `get_price` sends the header and the URL carries only `symbol`. Confirmed against the live API first (200 with header, 401 without). Two tests in `test_stocks.py` (header not URL; a logged 429 does not contain the key); mutation-checked by putting `token` back in the params.
- **WebSocket left as is:** `_listen` still puts `?token=` in the WS URL. Finnhub's REST docs allow the header ("All GET request..."), but a live handshake with the header only got 401 (the same as no auth), while the query param was recognised (429, a connection limit, probably from the app's own live connection). `websockets` 13.1 errors never contained the URL in the cases tried (refused, HTTP rejection, close 1011). Consider a comment at the `url =` line in `_listen` so nobody moves the token to a header.

### Minor

#### 4. Cross-router import
- [x] Fixed
- **File:** `api/activities.py:14`
- `api/activities.py` imports `get_ledger_cache` from `api/positions.py`. Move it to a shared `app/core/deps.py`. The same commit has unrelated formatter reflow hunks in `_import_one_account`.
- **Done:** `get_ledger_cache` now lives in `app/core/deps.py`; both routers import it from there. `positions.get_ledger_cache` is still the same object, so existing `dependency_overrides` keep working. The reflow hunks in `_import_one_account` were left alone.

#### 5. Silent-zero default for `invested_cad`
- [x] Fixed
- **File:** `services/ledger_cache.py`, `services/portfolio.py`
- `invested_cad` defaults to `0.0` on `LedgerSnapshot` and `build_summary`. A future caller that forgets it silently shows zero committed. Today's callers are covered by tests.
- **Done:** the field and the argument are now required. About 28 test call sites pass `invested_cad=0.0` explicitly. New `test_invested_cad_must_be_passed` pins it; mutation-checked by putting the defaults back.

#### 6. Float noise in `shares`
- [x] Won't fix (decided by author)
- **File:** `services/portfolio.py` (`merge_holdings`)
- `shares` leaves the API as e.g. `2.8341000000000003`. The page rounds it; other clients would not. Suggested rounding in `merge_holdings`.
- **Decision:** rounding is a display concern. The API keeps the data as computed (money and shares are unrounded, as `schemas/positions.py` documents) and each client formats for itself; the page does so in `fmtShares`.

#### 7. No hint when a refresh fails over old data
- [x] Fixed (needs a visual check, step 7 of `implementation.md`)
- **File:** `app/portfolio/page.tsx`
- When a poll fails but earlier data exists, rows stay on screen with no sign they are out of date (`positionsError && positions` shows nothing). The `stale` tooltips only cover upstream price failures. A small "refresh failed" note would help.
- **Done:** the Holdings header shows "Couldn't refresh. Showing the last data." when `positionsError && positions`. `tsc` and `next lint` clean; not checked in a browser.

#### 8. `TickerLogo` failure state is sticky
- [x] Won't fix
- **File:** `components/ui/ticker-logo.tsx`
- The component keeps `attempt`, the index of the logo URL being tried, and `onError` only moves it forward. USD symbols have two candidates (`xnas`, `xnys`), CAD symbols one. The browser does not tell a 404 from a dropped connection in `onError`, so a transient network error on the right URL is treated as "no logo here" and the ticker box is shown until the row remounts. Rows are keyed `${symbol}-${currency}` (`page.tsx`), so the 30s SWR refresh does not remount them; a reload or navigating away and back does.
- **Why not fixed:** the fix is retry timers or per-URL failure memory outside the component, which is extra state and timing logic for a cosmetic case. The fallback box shows the full ticker, it is already the designed state for ETFs and CDRs that have no logo, and nothing is lost.

#### 9. Unbounded per-key locks and caches
- [x] Won't fix
- **File:** `services/prices.py`, `services/asset_types.py`
- `_cache`, `_last_good` and `_locks` in `PriceService`, and the equivalent dicts in `AssetTypeService`, are keyed by `(symbol, currency)` and never shrink until the process restarts.
- **Why not fixed:** the only callers are in `api/positions.py`, and the pairs come from the author's own ledger holdings (`snapshot.holdings`); no request parameter or typed string becomes a key. Growth is bounded by the distinct symbols ever held in one process lifetime. Each entry is a small dataclass plus a lock, so even 1,000 symbols would be well under a megabyte, and a personal portfolio has a few dozen.
- **Revisit if:** a route or feature ever prices or classifies user-supplied symbols (for example a search box calling `get_price`). Then add a size cap or a TTL sweep.

### Praise
- `LedgerCache`: version counter discards a load that raced with an import, and `invalidate()` runs after the commit, never before. Tested.
- `portfolio.py`: `merge_holdings`, `build_rows`, `_allocate`, `build_summary` are pure; a test checks each dataclass matches its response schema field for field.
- `PriceService`: cache, per-key lock, negative cache and last-known fallback fit together; routing by native currency with the `currency_mismatch` guard stops a CDR being priced as the US stock (~25x error).
- `AssetTypeService`: never raises, has a timeout and a failure cache, and cannot affect price fields.
- Tests: ~870, with mutation checks on the key rules (missing-rate guard, FX conversion, cache invalidation) and real-app 401 tests; routes sit behind `verify_api_key`.
- Corrupt ledger becomes a 500 with a code, not a crash.
- No injection surface (ORM / PK lookups); `encodeURIComponent` and `referrerPolicy="no-referrer"` on logo URLs.
- Plan and docs kept in step with the code; follow-ups filed (#23, #73, #74).

### Questions for author
- Stays uvicorn single-process? The caches assume it (documented; Dockerfile has no `--workers`).
- `fmtShares` shows `3 Shares` for 2.83 and `1 Share` for 1.4. Deliberate choice; is it still acceptable?
- Should the `PriceService` yfinance timeout match `AssetTypeService`'s 5s?
- Is the stale-backend crash (page needs `invested_cad`, challenges #24) acceptable? Currently deliberately not guarded.

### Test coverage assessment
- [x] Happy path and error cases (backend)
- [x] Edge cases: empty ledger, missing rate, unpriced rows, zero cost, USD / CAD symbol collision
- [x] Hung yfinance call (added with #1)
- [ ] Frontend: no tests; matches the planned #29 suite

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
| 1 | _None yet_ | — | ⬜ Open |
