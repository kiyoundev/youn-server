# Issue #33: Implementation

Build order is inside-out: pure logic first (tested against a synthetic fixture), then persistence, then transport, then UI.

## Steps

### 1. Fixtures
- [x] Synthetic CSV under `backend/tests/fixtures/wealthsimple/` — fake `account_id`, fake values: deposit, e-Transfer, USD buy with `FX Rate`, CAD-listed buy (no FX), dividend, interest, NRT tax, **two same-day $0.01 interest rows differing only in description**, and a sell (`with_sell.csv`, placeholder strings). Expected derived values in the fixtures' `README.md`.
- [x] Variants: blank `effective_date`/`effective_time` (must reject), unknown-type row.
- [x] ~~Footer variant~~ — dropped 2026-09-22: never seen in a real export, only an unverified line in the original ticket text; the real 2026-09-20 export has no footer.
- [x] ~~Variant: US trade missing FX text~~ — dropped: no such rejection exists (`challenges.md` #11, decided 2026-09-21). Mixed-currency symbol variant is a step 4 test instead.
- [x] Confirm nothing derived from the real export is committed (account id, holdings) — fake id `TEST-ACCT-0001` differs from the one in `mock-market.ts`.

### 2. Parser — `services/wealthsimple_csv.py`
- [x] Header-driven `csv.DictReader` directly on the decoded text — no footer-stripping step (dropped 2026-09-22, unverified). `effective_at` = `effective_date` + `effective_time` only — a row with either blank is rejected (`missing_effective_date`), not dated from `settlement_date` (decided 2026-09-22: not expected in practice, and `settlement_date` runs ~1 day late on trades). No `transaction_date` column exists.
- [x] `currency` column must be `CAD` on every row (this is a CAD account; even USD stock trades are stamped `CAD` — distinct from the holding's *native* currency, inferred later from the FX text) → `unsupported_currency` otherwise (decided 2026-09-22).
- [x] Row-level parse errors (bad number, missing required field) are collected per row and checked *before* the type-allowlist pass (decided 2026-09-22: malformed rows win over unknown-type).
- [x] Explicit `(activity_type, activity_sub_type)` allowlist; collect *all* unknown combos (type, sub_type, direction, count, example description) then reject whole file.
- [x] `quantity` → shares only when `activity_type == "Trade"`; otherwise `quantity = None`.
- [x] Parse `FX Rate: x` from description into `fx_rate`, on every row type (interest rows carry it too). FX present → USD-native trade; absent → CAD-native. No rejection either way.
- [x] ~~Commission reconcile check~~ — dropped 2026-09-22: real export confirms commission is always `0` or blank (self-directed, commission-free trades); the column is still stored (per schema.md) but no validation runs on it.
- [x] Tests: `tests/services/test_wealthsimple_csv.py`, 18 cases — `_read_rows`, `_parse_row`, `_check_allowlist`, `parse_export`, against the fixtures, inline malformed cases, and a BOM check. Also sanity-checked ad-hoc against the real 2026-09-20 export (20/20 rows parse clean).

### 3. Import planner — `services/ledger_import.py`
- [x] Pure `plan_import(stored_range, rows)` per account: frozen boundary = `max(stored_earliest, newest − 7d)` (clamped for a stored range shorter than 7 days, challenges.md #2); prepend rows < earliest; replace the tail **only when the file reaches the newest stored row** (corrected in code review 2026-09-25 — it first keyed on the boundary, which deleted newer stored rows when an older export was re-uploaded); skip the frozen overlap; reject with `re_export_from` when a file that reaches the newest row doesn't reach back to the boundary. Boundary inclusive on the tail side (a row dated exactly on the boundary is replaced, not frozen).
- [x] Tests: `tests/services/test_ledger_import.py`, 13 cases (10 + 3 regression cases for a file that ends before the newest row) — first import, identical re-import, overlapping extension, prepend-only, gap rejection, file ending before the boundary (not rejected), short-stored-range clamp, boundary-day inclusivity, earliest-stored-date frozen (not prepended), both $0.01 rows survive an import and a re-import.

### 4. Positions — `services/positions.py`
- [x] `compute_positions` ordered by `effective_at` (sorted defensively inside, not trusted from the caller): buy adds shares + cost (`−net_cash_amount`); sell reduces shares at running average; native cost for USD = `unit_price ÷ fx_rate` per trade, weighted-averaged; CAD cost from cash paid. `ActivityLike` Protocol (structural typing) decouples this from both `ParsedRow` and the future `Activity` model.
- [x] Cash = sum of `net_cash_amount` over every row, checked for going negative after every row, not just at the end.
- [x] Integrity: shares/cash < 0 → raise (`negative_holdings`/`negative_cash`) with symbol/date; a symbol whose trades mix FX-present and FX-absent → raise `mixed_native_currency`; warn if earliest row isn't a funding deposit (`net_cash_amount > 0` on a `MoneyMovement` row).
- [x] Fully-sold-down-to-0 holdings excluded from the returned list (avoids a divide-by-zero on avg cost; a later re-buy starts a clean cost basis).
- [x] Return signature corrected to `(holdings, cash, warnings)` — `schema.md` originally sketched a 2-tuple, but the import response needs the deposit-history warning surfaced, which only this function can compute.
- [x] Tests: `tests/services/test_positions.py`, 11 cases — `base.csv`/`with_sell.csv` match `README.md` to the cent, sell keeps avg cost, the spec's own 300.00 CAD @ 1.4500 → 206.90 USD example, oversell/underfunded-buy/mixed-FX all raise, fully-sold position excluded from output, re-buy after a full sell starts a clean cost basis, deposit-history warning fires (and doesn't) correctly.

### 5. Model + migration
- [x] `models/activity.py`, export in `models/__init__.py`. Verified offline: imports clean, registers in `Base.metadata`, matches `schema.md`'s column table.
- [x] `alembic/versions/0018_activities.py` (docstring style of `0015`); `alembic history` confirms the chain (`0017 -> 0018 (head)`). **Not yet applied** — needs `alembic upgrade head` run against the real Postgres container (user's own docker workflow, not run by the assistant); `downgrade` also not yet verified round-trip.

### 6. Route — `api/activities.py`
- [x] `POST /api/activities/import`: read upload → `parse_export` → per account load stored rows/range → `plan_import` → project merged ledger → `compute_positions` integrity check → apply (delete tail, insert) in **one transaction** (single `db.commit()` after every account succeeds) → return `ImportResult` with coverage message. Multi-account file handled — grouped by hand (not `itertools.groupby`, which only groups consecutive runs), not rejected.
- [x] `DELETE /api/activities?account_id=`.
- [x] Registered in `main.py` behind `verify_api_key`, same pattern as the other 7 routers; pydantic schemas in `schemas/activity.py`. Verified offline: both routes present on `router.routes` and on the full `app.routes` after import — no live DB needed for this check.
- [x] Route tests in the existing mocked-DB style; assert no write on any rejection — `tests/api/test_activities_routes.py`, 6 cases: first-time single-account success, unknown-type rejection (zero DB calls), coverage-gap rejection, negative-cash rejection (compute_positions' gate, after plan_import already succeeded), multi-account file (one transaction, not one commit per account), reset route.
- [ ] **Not yet live**: needs migration `0018` applied (`alembic upgrade head`) and the backend container rebuilt (`docker compose build backend && up -d backend` — no bind mount/`--reload`, confirmed from the Dockerfile) before this is reachable on the real server.

### 7. Frontend
- [x] `app/api/proxy/activities/import/route.ts`: forward raw body + `Content-Type`, `X-API-Key`, `cache: "no-store"`; relay status/body. Body buffered via `arrayBuffer()` (not streamed) — matches the catch-all's own `request.text()` approach, avoids Node fetch's `duplex: "half"` requirement for a streaming body. Verified offline: `tsc --noEmit` and `eslint` both clean. Not yet tested against a running dev server/container (user verifies frontend changes themselves).
- [x] `nav.tsx` + new `lib/api/activities.ts`: POSTs the `File` as `FormData` (no `Content-Type` header — the browser sets it with the multipart boundary); `isImporting` swaps the Upload icon for a `LoaderCircle` spinner and disables the button (same pattern as the watchlist's rescrape-all); success toast is just "Import complete" (simplified 2026-09-24 from an added/replaced/skipped + coverage message; the counts and the "next time export from …" advice are still in the API response's `accounts[0]`, and the advice still reaches the user when a too-short export is rejected — `coverage_gap` names the date to re-export from); rejection toast shows **only** the `message` (decided 2026-09-24, replacing the copy-pasteable-detail plan), persisted; the full structured detail is `console.error`'d so extras like `unknown_activity_type`'s `types` stay retrievable; input value cleared in a `finally`; the old filename label removed. `ApiError.detail` stays a plain string — the helper collapses object/array/string `detail` shapes into one message, so no widening/`payload` needed. Warnings skipped for now. Verified offline: `tsc --noEmit` + `eslint` clean; **not run in a browser** (user verifies frontend changes).

### 8. Docs
- [x] `.doc/database.md`: diagram regenerated with `paracelsus inject` (adds `activities`); `Activity` added to the hand-written Models block; new Key Design Decisions entries (derived positions, no unique key, timezone).
- [x] `.doc/api.md`: new "Activities (Wealthsimple Import)" section (routes, merge semantics, full rejection-code table, the sell-rejected-on-purpose note, the multipart proxy) + `AccountImportResult`/`ImportResult` TypeScript interfaces.
- [x] `.doc/issues.md`: Status line updated, 12 of 13 acceptance criteria ticked (the sell-strings one stays open — it needs a real sell), implementation notes added. The issue header, Progress Tracker row and feature-area index are deliberately **left open** until step 9's remaining checks and step 10's cleanup are done.

### 9. Validation
- [x] Manual, part 1: real export imported locally (via curl, then via the nav upload), and re-imported with no change (0 added, 2 replaced, 18 skipped).
- [x] Code review 2026-09-25 (`review.md`): 1 Critical + 1 Major + 4 Minor fixed, 1 Major fixed with a live check still owed (the advisory lock), 2 decided as-is. Backend + frontend need a rebuild to pick these up.
- [ ] Manual, part 2 (user, live): a trimmed export that should hit `coverage_gap`; `DELETE /api/activities` + full re-import; `SELECT count(*)` still 20 after the UI re-import.
- [ ] Verification items (need real data): after the next trade export immediately and a day later; after the first sell send the real row so its strings can be mapped.
- [x] `pytest` and frontend `npm run lint` — 2026-09-25: lint clean; backend 487 pass, the 5 `tests/scheduler/test_jobs.py` broadcast failures are pre-existing and unrelated (same failures with only that file running; `jobs.py` untouched).

### 10. Cleanup
- [x] Both `__main__` scratch blocks removed (`wealthsimple_csv.py`, `positions.py`) — they hardcoded a local Downloads path and one printed rows in full; the 53 #33 tests pass without them.
- [x] No real export or account id in git — the only hit for the real account id is the pre-existing `frontend/src/lib/mock-market.ts` (already in the spec's security note, out of scope here).
