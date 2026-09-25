# Issue #33: Review

## AI Review
<!-- Run 2026-09-25 with the code-reviewer skill, before the first commit -->

**Intent:** turn an uploaded Wealthsimple export into a durable per-account ledger of `Activity` rows, merge overlapping uploads by date range (no row identity), and derive holdings/cash from it. **Verdict: Comment** — the blocking issues were fixed in this pass; of the three open Majors, #3 and #5 are now resolved and only #4 still needs a decision before this goes to the Pi.

Stage 1 (spec compliance) was done before Stage 2 (quality). The stage-1 finding was the serious one.

### Critical — fixed
1. **`ledger_import.py` — tail refresh keyed on the boundary, not the newest row (silent data loss).** The spec says the tail is refreshed *only when the file reaches the newest stored row*; the planner used `file_newest >= boundary`. A file ending between the boundary and the newest stored row (e.g. re-uploading an older export) deleted every stored row after its last row and had nothing to put back. Reproduced with a script before touching anything. Now `reaches_newest = file_newest >= stored_newest`; a file that ends earlier can only prepend, and its tail-window rows are skipped. Two of my own tests had encoded the bug (files ending before the newest row asserting a tail replace) and were corrected; three planner tests + one route test now cover it, and were confirmed to **fail against the old code**.

### Major — fixed
2. **`wealthsimple_csv.py` — a `Trade` row with a blank symbol/quantity/unit_price returned a 500.** `compute_positions` asserts all three; the parser never checked them. Now a `malformed_row` 422 (also for quantity <= 0).

### Major — resolved or open
3. **[Decided 2026-09-25: leave as is]** **The "re-export from <date>" advice can dead-end on sparse activity.** The reach-back check uses the file's *first row* as a proxy for the export's start date. Real example: newest stored row is Sep 15, so the boundary is Sep 8, but nothing happened Sep 8–14 — an export starting Sep 8 contains rows only from Sep 15, is rejected, and the message says "re-export from 2026-09-08 or earlier" again. Going wider always works. Options were (a) advise the date of the newest stored row on/before the boundary, or (b) reword. **Decision: keep the message unchanged** — the success toast no longer shows any "export from" advice, so this text only appears on a rejection, and a wide export (the intended workflow) never hits it. Narrow exports are the only way to reach the dead end; going wider always works.
4. **[Decided 2026-09-25: documented deviation, not enforced]** **Older-side contiguity isn't enforced.** The spec says an export must be "contiguous with the stored range on the older side"; a prepend-only file is accepted with any gap (verified: Nov 5 accepted against a ledger starting Jan 1). Same first-row-as-proxy limit applies, so the only available check is "the file must reach the earliest stored row". Options were to enforce that (new `coverage_gap` variant, ~6 lines + a test) or document the deviation. **Decision: document it.** The account starts at its first deposit, so there is no older history to import, and the only way to hit this is to deliberately import a partial old file. Recorded in `ledger_import.py`, `api.md` and the spec's implementation notes; revisit if older history ever needs importing.
5. **[Fixed 2026-09-25]** **No concurrency guard on import.** Two overlapping imports (or an import racing a reset) can both plan against the same stored range and double-insert; there is no unique constraint to catch it. The UI disables the button while importing, but the API doesn't stop a second `curl`. Fixed with a transaction-scoped `pg_advisory_xact_lock(33, hashtext(account_id))` per account, taken before anything is read, in sorted account order (so two concurrent multi-account imports can't deadlock) — and by the reset route too, so an import racing a reset is also serialized. Released automatically at commit/rollback. Four route tests cover the ordering and that a rejected file never takes a lock. **The SQL itself is not yet verified against a real Postgres** (Docker was down when this was written) — re-run the two-session check (same account blocks, different account doesn't, released after the transaction) once the DB is up.

### Minor — all fixed 2026-09-25
6. **[Fixed]** `positions.py` classifies a trade as a buy by `net_cash_amount < 0`, so a $0 buy (a bonus share) is treated as a sell and rejected as `negative_holdings` (verified). `<= 0` is safer — a $0 sell can't happen. Low likelihood: the allowlist only admits `Trade`/`BUY`.
7. **[Fixed]** No upload size limit, and the proxy `fetch` has no timeout of its own — if the backend hangs, the nav button spins until Node's built-in fetch limit (about 5 minutes, as far as I know) instead of failing fast. Fine for one user; Fixed with a 5 MB cap on both sides (the proxy refuses on `Content-Length` before buffering; the backend reads at most cap+1 bytes and returns `413 file_too_large`) and a 30 s `AbortSignal.timeout` on the proxy fetch, which now answers 504 ("took too long") or 502 ("couldn't reach the backend") instead of a bare 500.
8. **[Fixed]** On a first import the "kept rows" query always runs and always returns nothing (one wasted SELECT). The query is now skipped when nothing is stored.
9. **[Fixed]** `compute_positions` uses `assert` for a Trade row's required fields — now guaranteed by the parser, but asserts vanish under `python -O`. Now an explicit check raising `malformed_row`, which also keeps the type narrowing.
10. **[Found and fixed while testing the size cap]** A large non-CSV text file (one field over 128 KB) made Python's `csv` module raise its own `csv.Error`, which nothing caught — a 500. It's now `invalid_file`.

### Praise
- Three pure modules + a thin route, so all the risky logic is unit-tested with no DB; the seams (`ActivityLike` protocol, one shared `LedgerImportError`) are clean.
- Every parser assumption was checked against the real export and dropped when wrong (`transaction_date`, the footer, the settlement fallback, commission) instead of being built. The timezone assumption is well supported too: trades land at 09:30:0x, i.e. Eastern local market open, not UTC.
- Rejecting the whole file on an unknown type keeps a re-upload working after the mapping is added — a skipped row would have been stranded by the frozen-past rule.
- The `jsonable_encoder` bug was caught by testing through the real response layer, and there are now tests at that layer.

### Questions
- For 3 and 4: which option? Both come from the same limitation — an export doesn't record its requested date range, so "first row" is the only evidence available.
- Housekeeping: two greps early in this session printed secrets from `.env` into the transcript (the API key and a commented-out old NAS DB password). Only matters if the transcript is shared or logged; rotate if so.

### Test coverage assessment
- [x] Happy path (first import, re-import, extension, multi-account)
- [x] Error cases — every rejection code, through the real response layer for the ones carrying datetimes
- [x] Edge cases — boundary inclusivity, short stored range, same-day lookalike rows, BOM, non-UTF-8, Trade rows missing fields
- [x] Write path — the tail-replace DELETE, and all-or-nothing across accounts (both added in this review; neither existed)
- [x] Concurrency — lock ordering and coverage are route-tested with a mock; real blocking behavior still needs the live two-session check
- [ ] Not covered: nothing runs against a real Postgres except the manual live import

---

## Tech Lead Review
<!-- Populated when PR review comments arrive -->

| # | Comment | File / Line | Status |
|---|---------|-------------|--------|
