# Issue #33: Wealthsimple Activity Import (Parse, Persist & Derive Positions)

## PR / Branch
- **Branch:** `feature/33-wealthsimple-activity-import`
- **PR Title:** `main | feature - 33 - Wealthsimple activity import`
- **Note:** this repo doesn't use branches (solo project, direct commits to `main`) — fields kept nominal for template consistency.

## Task Status
| Step | Status | File |
|------|--------|------|
| Context & Planning | ✅ Done | [context.md](context.md) |
| Schema & API Contract | ✅ Done | [schema.md](schema.md) |
| Implementation | ✅ Done 2026-09-26 — follow-ups (real sell strings, settlement-date check, live-DB checks) listed at the end of #33 in `.doc/issues.md` | [implementation.md](implementation.md) |
| Challenges | ✅ Done | [challenges.md](challenges.md) |
| Review | 🟡 AI review run 2026-09-25 — 1 Critical + 1 Major fixed; 3 Major open (decisions) | [review.md](review.md) |

## Success Criteria
- [x] `Activity` model + migration `0018` match the confirmed 2026-09-20 CSV shape
- [x] Parser is header-driven: `effective_date`/`effective_time` required on every row (rejects if blank); no footer handling (dropped 2026-09-22, never confirmed in a real export)
- [x] Unknown `(activity_type, activity_sub_type)` rejects the whole file before anything is stored, with a copy-pasteable error
- [x] `quantity` is read as shares only for `Trade` rows
- [x] Coverage tracked per account; export not reaching back to newest stored date − 7 days is rejected with the date to re-export from
- [x] Frozen past untouched; rows before earliest stored date prepended; tail replaced; re-uploading the same file changes nothing
- [x] Both same-day $0.01 interest rows survive import and re-import
- [x] `compute_positions` yields expected shares, native + CAD average cost, cash balance on a synthetic fixture; buy cost = cash actually paid
- [ ] Buys and sells both handled (weighted-average cost); negative shares/cash fails loudly *(built and tested with placeholder sell strings — open until a real sell is seen and mapped)*
- [x] USD holding native cost = per-trade `unit_price ÷ fx_rate`; a trade without FX text is CAD-native (no rejection); a symbol mixing both fails loudly
- [x] `DELETE /api/activities?account_id=` resets one account's ledger (backend only — no UI, decided 2026-09-21) *(route-tested; not yet run against the live DB)*
- [x] Frontend file input POSTs the `File` as multipart; success shows "Import complete", a rejection shows its `message` in a persistent toast (simplified 2026-09-24 from summary + coverage message + full detail)
- [x] No real export committed; tests use a synthetic fixture
- [x] `.doc/database.md` and `.doc/api.md` updated

## Estimated Effort
- Implementation: **~6h** (parser + planner + positions ~4h, route/migration ~1h, frontend + proxy ~1h)
- Testing: **~2h**
- **Total: ~8h** (matches the issue estimate)
