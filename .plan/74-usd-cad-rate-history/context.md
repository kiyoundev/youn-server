# #74: Context

## Issue Description

`fx_rates` holds one row per currency, the latest rate only (`services/fx.py` refreshes it daily from Frankfurter; `FxRate` is "never a history table"). #23's portfolio value chart needs the USD→CAD rate **for past dates**, to value USD holdings on each day of a range — the live rate only answers "what's it worth today," never "what was it worth on March 3rd."

This matters because two independent things move a USD holding's CAD value on any given day: the stock's own USD price, and the USD→CAD rate itself. A chart that reuses today's rate for every past point would be wrong by however much the rate has moved since — not a rounding error, a real distortion that gets worse further back in the range.

This is also deliberately a different number from `invested_cad` ("Committed"): that figure is frozen at each trade's own `Activity.fx_rate` (the rate Wealthsimple recorded at purchase time, which runs ~2% above market as their markup) — correct for "what you paid," wrong for "what it's worth on some other day." #74 is exclusively about the second question.

**Resolved design** (see `challenges.md` for the reasoning):
- New table, `fx_rate_history` — `FxRate` and its read path (`GET /api/fx-rates`, #19's `balance_cad`) are untouched.
- Lazy, write-through cache: reads check the table first, fetch only missing dates from Frankfurter, persist, return. No separate backfill job — first real request for any date range fills it.
- `refresh_fx_rates_job` also writes today's single rate into the new table (same fetch call it already makes).
- Backend-only — no new API route. #23's future route is the only caller.
- Weekend/holiday gaps: carried forward from the last known rate, computed at read time, never stored.
- A date that can't be resolved (upstream failure, or earlier than Frankfurter's own coverage) is simply omitted from the result — never raised, never a fabricated/wrong rate. The chart (#23) will connect across the missing point the same way it already connects between every other adjacent pair of real points.

### Acceptance criteria (from the issue doc)
- [ ] A function returns the USD→CAD rate for any past date, and for a date range as a series
- [ ] A date with no published rate (weekend, holiday) gets the last earlier rate; a date before the first available one is a clear error, not 0 or 1
- [ ] The chosen source is the same one the live `fx_rates` refresh uses, or the decision to differ is written down with its effect on the chart's last point
- [ ] A failed upstream call returns an error the caller can handle, never a wrong rate
- [ ] Tests cover the weekend carry-forward and the failure path (network mocked)

(The "date before the first available one is a clear error" and "returns an error the caller can handle" criteria are satisfied by omission-from-result rather than a raised exception — see `challenges.md` for why that's equivalent here: nothing downstream currently differentiates "never requested" from "failed to fetch," and the chart renders correctly either way.)

## Component / Route Summary

### Current State
- `app/models/fx_rate.py`: `FxRate`, `currency` as primary key — exactly one row per currency, upserted in place.
- `app/services/fx.py`: `fetch_fx_rates()` hits `GET https://api.frankfurter.dev/v1/latest?base=CAD&symbols=USD,KRW`, inverts CAD-based rates to X→CAD. `refresh_fx_rates()` overwrites the one `FxRate` row per currency.
- `app/scheduler/jobs.py`: `refresh_fx_rates_job` runs every 24h **from process boot time** (not midnight-anchored) — same pattern as the only other scheduled job, `poll_prices_job`. A restart resets this timer.
- `app/api/fx.py`: `GET /api/fx-rates` reads the live `FxRate` rows, flags `stale` if `fetched_at` is older than 24h (`STALE_THRESHOLD_HOURS`).
- Nothing in the codebase currently looks up a past FX rate for any date.

### Target State
- `app/models/fx_rate_history.py` (new): `FxRateHistory`, one row per `(currency, date)`, unique constraint on that pair.
- `app/services/fx.py`: new `get_rate_history(currency, start, end) -> dict[date, float]` — reads what's cached, fetches only the missing dates from Frankfurter's range endpoint (`base=CAD&symbols={currency}`, same inversion convention as `fetch_fx_rates`), upserts them, fills weekend/holiday gaps at read time, omits any date that couldn't be resolved.
- `app/services/fx.py`: `refresh_fx_rates()` also upserts today's already-fetched rate into `fx_rate_history`, inside its existing per-currency loop, before its existing single `commit()` — one atomic write covering both tables. `app/scheduler/jobs.py` is untouched; `refresh_fx_rates_job` keeps calling the same function it already does.
- `.doc/database.md`: regenerated to include the new table.

## Impact & Risk

### Files Changed
- **`app/models/fx_rate_history.py`** — new model
- **`backend/alembic/versions/0021_fx_rate_history.py`** — new migration (additive: one new table, no change to `fx_rates`)
- **`app/services/fx.py`** — add `get_rate_history()` and its Frankfurter-range-fetch helper; `refresh_fx_rates()` gains the dual-write into `fx_rate_history`
- **`backend/tests/services/test_fx.py`** — new tests for `get_rate_history()` and for `refresh_fx_rates()`'s dual-write
- **`.doc/database.md`** — regenerated diagram (new table appears)
- **`.doc/issues.md`** — tick #74 once shipped

### Dependencies
- **`app/services/fx.py`'s existing `fetch_fx_rates`/`refresh_fx_rates`** — untouched; the new function sits alongside, doesn't modify them
- **Frankfurter (`api.frankfurter.dev`)** — same host, same no-auth setup, now also queried for date-ranged history, not just `/latest`

### New Dependencies
None — same `httpx` client already used by `fetch_fx_rates`.

### Breaking Changes
None. Purely additive: new table, new function, one new line in an existing job. `FxRate`, `refresh_fx_rates`, and `GET /api/fx-rates` behave identically to today.
