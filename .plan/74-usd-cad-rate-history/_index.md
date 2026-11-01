# #74: USD→CAD Rate History (Source for Past Portfolio Values)

## PR / Branch
- **Branch:** `feature/74-usd-cad-rate-history`
- **PR Title:** `main | feature - 74 - USD-CAD rate history`

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Implementation | 🟡 In progress (steps 1-4 done; migration not yet applied) | [implementation.md](implementation.md) |
| Challenges | ⬜ Not started | [challenges.md](challenges.md) |
| Review | ⬜ Not started | [review.md](review.md) |

## Success Criteria
- [x] `get_rate_history(session, currency, start, end)` (`app/services/fx.py`) returns the USD→CAD rate for every resolvable date in range
- [x] A date already cached in `fx_rate_history` is served from the DB — no Frankfurter call
- [x] A date missing from the cache is fetched from Frankfurter's range endpoint, persisted, and returned, in the same call
- [x] A weekend/holiday date (no published rate) returns the last earlier known rate, computed at read time — never stored as a duplicate row
- [x] A date that fails to resolve (upstream failure, or earlier than Frankfurter's coverage) is omitted from the result — logged, never raised, never a fabricated rate
- [x] `refresh_fx_rates()` additionally upserts today's fetched rate into `fx_rate_history` (same commit as the `FxRate` write), so the live total and the history table's "today" point never disagree
- [x] Upserts into `fx_rate_history` are idempotent on `(currency, date)` — safe against the scheduler's boot-anchored (not midnight-anchored) timing writing more than once in a calendar day
- [x] `FxRate`, `refresh_fx_rates`'s existing behavior, and `GET /api/fx-rates` are unchanged for everything that was already working — this issue is additive only
- [x] `.doc/database.md` regenerated (`paracelsus inject`) to include the new table
- [ ] Migration `0021_fx_rate_history.py` actually applied — local + remote (user doing this once the issue is fully done)
- [x] #74 ticked in `.doc/issues.md`

## Estimated Effort
- Implementation: **2h**
- Testing: **1h**
- **Total: ~3h** (re-estimated from the issue doc's "~2h rough" now that the design — new table, lazy write-through cache, no new route — is settled)
