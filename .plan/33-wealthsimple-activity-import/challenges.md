# Issue #33: Challenges & Notes

## Potential Challenges
1. **Planner correctness (frozen past / tail / prepend)** — a subtle off-by-one silently duplicates or drops rows and is invisible until positions look wrong. Mitigation: keep `plan_import` pure with exhaustive table-driven tests (first import, idempotent re-import, extension, prepend-only, gap, file ends early). Decide and test boundary inclusivity explicitly (row on exactly newest − 7d).
2. **Stored range shorter than 7 days** — `newest − 7d` can fall before the earliest stored date. Treat the whole stored range as tail in that case; cover with a test.
3. **Unmappable sells** — the sell `activity_sub_type`/`direction` strings are unconfirmed. Unknown types reject the whole file *by design*, so the first real sell will fail import until its strings are sent and mapped. Not a bug; document it in the error text and the verification items.
4. **Integrity check needs the merged ledger** — negative shares/cash can only be judged on stored-plus-incoming rows after the planner runs, so the check must run before commit and roll back. Mitigation: project the merged list in memory, run `compute_positions`, then write.
5. **No real-DB test harness** — existing route tests mock the session, so transaction atomicity isn't exercised. Mitigation: keep all decision logic in pure functions; keep the DB layer to load-range / delete-tail / bulk-insert; manually verify atomicity against the local Postgres with a deliberately failing import.
6. **Multipart through the Next proxy** — the catch-all proxy calls `request.text()` and forces JSON `Content-Type`, which corrupts or drops the multipart boundary. Mitigation: dedicated route forwarding `request.arrayBuffer()` (or the stream) with the original `Content-Type`; check the body-size limit for a large export.
7. **Same-day collisions and ordering** — automatic postings have `00:00:00` times, so ordering within a day is by insertion. Positions only depend on `Trade` rows (which have real times), so this affects nothing derived, but don't add a unique key that would reject the legitimate $0.01 pair.
8. **Float money** — cost and cash accumulate floats; use `round(...)` at output and compare with tolerance in tests. Note `Numeric` was not chosen to match the rest of the schema (`Float` everywhere).
9. **Account number exposure** — `frontend/src/lib/mock-market.ts` holds a real account id (commit `5ec2f2a`). Out of scope here, but replace before the repo goes public; tests must use a fake id.
10. **Reset is destructive and UI-less** — a wrong `account_id` deletes nothing (0 rows) but a right one wipes the ledger. Acceptable because the CSV is the recovery path. If resets become routine, add a confirm-guarded button later.

11. **RESOLVED 2026-09-21 — no "US trade without FX text" rejection.** A CAD-hedged CDR (e.g. `AVGO`) has no `.TO` suffix and no FX text, and every row is `currency: CAD`, so a US trade missing its FX text can't be told apart from a CDR. Decision: FX text present → USD-native; absent → CAD-native, no rejection (spec's own "one without it is CAD-native"). **Residual risk:** if Wealthsimple ever omits the FX text on a real US trade, that holding silently becomes CAD-native with a CAD cost basis, and #19 would quote it against the wrong market. Mitigation: a symbol whose trades disagree on FX presence fails loudly in `compute_positions` (mixed native currency), which catches partial omissions; a wholly omitted symbol can't be caught. *(Confirmed 2026-09-22 against the real export — an `AVGO - Broadcom CDR (CAD Hedged)` trade row has no `FX Rate:` text, exactly as predicted.)*
12. **Original spec text ≠ verified fact — three corrections this session, one pattern.** `transaction_date` (never existed), the `settlement_date` fallback (invented to explain it), and the `"As of ... GMT-04:00"` footer (dropped 2026-09-22 — never seen in any real export, only asserted in the ticket's own write-up about an unverified 2026-07-29 sample) all trace back to spec prose written before a real export was in hand. None were malicious or careless — they were reasonable-sounding claims about an old sample nobody could re-check at ticket-writing time. Lesson for the rest of this issue: treat any remaining unconfirmed claim in `.doc/issues.md`'s #33 write-up (e.g. the sell strings, per #3 above) as a hypothesis, not a fact, until checked against `/Users/youn/Downloads/activities-export-2026-09-20.csv` or a future real file.

## Key Differences
| Aspect | Current | Target |
|--------|---------|--------|
| Holdings source | none (planned manual `Position` table in #19) | derived from `Activity` ledger on read |
| Nav CSV input | keeps filename only | POSTs file, shows summary + coverage |
| Frontend proxy | JSON only | plus dedicated multipart route |
| Dedup | proposed row-matching key (collides on real data) | none — coverage + frozen past + tail replace |

## Rollback Plan
1. `alembic downgrade 0017` drops `activities`; revert the commit.
2. Verify the backend boots and `GET /api/fx-rates` still responds; nav CSV button reverts to filename-only.
