# #74: Implementation

## Steps

### 1. Data layer
- [x] `app/models/fx_rate_history.py`: `FxRateHistory` — `id` (PK), `currency` (str), `date` (Date), `rate_to_cad` (Float), unique constraint on `(currency, date)`. No `fetched_at` — a historical rate doesn't have a meaningful "staleness," only "do we have it or not" (see `context.md`)
- [x] Alembic migration `0021_fx_rate_history.py` — additive only, no change to `fx_rates`; chain verified (`0020 -> 0021`), not yet applied (DB unreachable from the dev machine right now — user will migrate local + remote once the issue is done)
- [x] Regenerate `.doc/database.md` (`paracelsus inject .doc/database.md app.models.base:Base --import-module app.models`, from `backend/`)

### 2. Service layer (`app/services/fx.py`)
- [x] `get_rate_history(session, currency, start, end) -> dict[date, float]`:
  1. Query `fx_rate_history` for `(currency, date)` between `start - 10d` (carry-forward lookback) and `end` — build the known-dates set
  2. For any date in `[start, end]` not already known, call `_fetch_rate_range()` once for the whole missing span
  3. Only add rows for dates genuinely new (not already in `known`) — a non-contiguous `missing` set's `min..max` can re-cover already-cached dates in between, and re-adding one would violate the `(currency, date)` unique constraint (caught this while implementing, see `review.md`)
  4. Walk `[start, end]` day by day; carry forward the nearest earlier known rate for a gap, without advancing `last_known` past it, so a multi-day holiday all carries the *same* anchor rate rather than drifting
  5. A date whose fetch genuinely failed (`_fetch_rate_range` returned `None`, not an empty-but-successful dict) is **never** carried forward, even if an earlier rate exists — distinguishing "Frankfurter said no data" from "we couldn't even ask" is why `_fetch_rate_range` returns `None` on failure rather than `{}`
- [x] `_fetch_rate_range(currency, start, end) -> dict[date, float] | None` — reuses the existing `httpx.AsyncClient` pattern (`follow_redirects=True`, `_FX_TIMEOUT_SECONDS`), no second divergent client setup
- [x] `refresh_fx_rates()`'s dual-write — added inside its existing per-currency loop, before its existing single `commit()`

### 3. Testing (`backend/tests/services/test_fx.py`, `respx` + `MagicMock` session, same convention as the existing `fetch_fx_rates`/`refresh_fx_rates` tests) — done, 16/16 passing, 888/888 across the full suite
- [x] Cache hit: all requested dates already in `fx_rate_history` → zero Frankfurter calls (`test_get_rate_history_cache_hit_makes_no_frankfurter_call`)
- [x] Cache miss: some dates missing → one range call for the missing span, results persisted, full series returned (`test_get_rate_history_cache_miss_fetches_and_persists_missing_range`)
- [x] Weekend/holiday carry-forward, same anchor rate across the whole gap, never written back as a duplicate row (`test_get_rate_history_carries_forward_across_a_weekend`)
- [x] Upstream failure: affected dates absent from the result, no exception propagates (`test_get_rate_history_omits_dates_when_the_range_fetch_fails`)
- [x] A failed fetch does **not** get carry-forward treatment even when an earlier real rate exists — the specific distinction `_fetch_rate_range`'s `None`-vs-`{}` return exists for (`test_get_rate_history_does_not_carry_forward_across_a_failed_fetch`)
- [x] Regression for the non-contiguous-`missing`-span bug caught while implementing: already-cached dates sitting inside a re-fetched range must not be re-added (`test_get_rate_history_does_not_readd_already_cached_dates_inside_a_refetched_span`)
- [x] `refresh_fx_rates()`'s dual-write: writes today's history row with the same rate written to `FxRate` (`test_refresh_fx_rates_also_writes_todays_history_row`), and overwrites rather than duplicates on a same-day rerun (`test_refresh_fx_rates_updates_existing_history_row_in_place`)
- [x] Fixed 2 pre-existing tests that the dual-write would otherwise have broken (`test_refresh_fx_rates_upserts_both_rows`, `test_refresh_fx_rates_updates_existing_row_in_place`) — `session.add` now also receives `FxRateHistory` objects, which share the `.currency` attribute with `FxRate` and would have collided in the old shared-dict mock helper

### 4. Cleanup
- [x] `ruff` clean on every touched file (no `mypy` configured in this project)
- [x] Tick #74 in `.doc/issues.md`'s acceptance criteria (no Progress Tracker row exists for #74 — table ends before it)
