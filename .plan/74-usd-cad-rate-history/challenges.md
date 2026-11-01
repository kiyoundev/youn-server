# #74: Challenges & Notes

## Potential Challenges

1. **Scheduler's boot-anchored, not midnight-anchored, timing** — `refresh_fx_rates_job` runs every 24h from process start, not at a fixed wall-clock time. A container restart can make `refresh_fx_rates()` fire twice within one calendar day, or skip a day if the process is down across a boundary. Mitigate: the dual-write into `fx_rate_history` is an **upsert on `(currency, date)`**, not a plain insert — a same-day rerun just overwrites today's row with the same (or a slightly re-fetched, still-correct) value, no unique-constraint error. The downtime-gap case needs no special handling at all: it's structurally the same as any other missing date, and `get_rate_history`'s normal cache-miss path fills it in whenever a chart next asks for that range.

2. **Frankfurter has already changed shape on us once** — `fetch_fx_rates`'s own comments document a real incident: `frankfurter.app` → `frankfurter.dev` silently broke every scheduled run until caught live. Mitigate: `get_rate_history` reuses the exact same `httpx.AsyncClient` setup (`follow_redirects=True`, same timeout, same host) rather than a second bespoke client — one place to fix if it happens again, not two.

3. **Carry-forward at a range boundary with nothing earlier to carry from** — if the very first date requested is itself a non-trading day and the table has no earlier row for that currency (e.g. the very first call this feature ever makes), there's nothing to carry forward. Resolved by treating it the same as any other unresolvable date: omit it from the result. No special-case branch — in practice unreachable for this app anyway, since Frankfurter's coverage goes back to 1999 and this app's ledger starts in 2026.

4. **KRW is in scope for the function signature but has no caller** — `get_rate_history` stays generic over `currency` (per the issue's own ask), but today only `"USD"` is ever requested, since `Holding.native_currency` is `Literal["CAD", "USD"]` (no KRW positions exist). Not worth adding KRW-specific test coverage beyond what genericity already gives for free — if a caller ever passes `"KRW"`, the same code path just works, untested-for-that-value until something actually needs it.

5. **Why omission-not-exception satisfies the issue's "returns an error the caller can handle" criterion** — the original issue text implies a signal the caller can act on. In the resolved design (see `/plan-issue #74`'s grill-me discussion), the chart's own rendering doesn't distinguish "this date was never requested" from "this date failed to fetch" — both just mean "no point here, connect across it" (recharts' default `connectNulls={false}` behavior isn't even invoked, since the date is omitted from the series entirely rather than present-as-null). Given nothing downstream differentiates the two cases, a raised exception would add a catch-and-discard step for no behavioral gain. If a future caller ever needs to tell "missing because never asked" apart from "missing because it failed," that's the point to revisit this, not now.

## Key Differences

| Aspect | Current (`FxRate`) | New (`FxRateHistory`) |
|---|---|---|
| Rows per currency | Exactly one, always | One per `(currency, date)` ever resolved |
| Write pattern | Overwrite in place | Upsert by `(currency, date)`; additive over time |
| Staleness concept | Yes — `fetched_at` vs. `STALE_THRESHOLD_HOURS` | None — a historical rate is either known or not, never "stale" |
| Populated by | `refresh_fx_rates()`, every ~24h via the scheduler | Same function, same call, same commit (today's date) **+** lazy fetch-on-read for any other date |
| Failure handling | Leaves the existing row untouched, logs a warning | Omits the unresolved date from the result, logs a warning |

## Rollback Plan
1. Revert the migration (`alembic downgrade`) — drops `fx_rate_history` only; `fx_rates` was never touched, so this has zero effect on the live rate, `GET /api/fx-rates`, or #19's `balance_cad`.
2. Revert the few added lines inside `refresh_fx_rates()` (the dual-write) — `app/scheduler/jobs.py` was never touched, nothing to revert there.
3. Verify `GET /api/fx-rates` and `/api/portfolio/summary` behave identically before and after — neither reads the new table, so this should be a no-op check, not a real risk.
