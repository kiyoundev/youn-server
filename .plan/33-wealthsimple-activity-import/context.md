# Issue #33: Context

## Issue Description
Turn an uploaded Wealthsimple "activities export" CSV into a durable ledger of `Activity` rows and derive holdings (shares, average cost, cash) from it. The ledger is the source of truth; no manually maintained `Position` table. Positions are derived on read; nothing derived is stored. Full spec and acceptance criteria: `.doc/issues.md` → "Issue #33" (design settled 2026-09-20).

Decisions added while planning (2026-09-21):
- **Multipart proxy:** dedicated Next.js route `app/api/proxy/activities/import/route.ts` forwarding the raw body + `Content-Type`; the JSON catch-all proxy is untouched.
- **Reset ledger:** backend only — `DELETE /api/activities?account_id=X`. No UI button (rare, destructive; curl with the API key is enough).
- **`effective_at` timezone:** CSV times are naive; store as tz-aware `America/Toronto` (Wealthsimple is a Canadian broker; EST/EDT is the reasonable default — not tied to the footer's `GMT-04:00`, which turned out to be unverified, see `challenges.md`). Reach-back logic keys on `effective_date`, so this only affects ordering.
- **Multi-account file:** coverage + import run per `account_id` inside one transaction; a multi-account file is not rejected.
- **Read surface:** #33 ships `compute_positions` only. #19 owns the read endpoints.

## Component / Route Summary

### Current State
- No CSV, ledger or position code in the backend.
- Latest migration is `0017`. Models follow `models/fx_rate.py` style (docstring citing the issue, `Mapped[...]` columns). Routers follow `api/fx.py`, registered in `main.py:93-100` with `Depends(verify_api_key)`.
- `python-multipart` already in `backend/requirements.txt`.
- Frontend: `components/nav.tsx:63` `handleCsvSelect` stores only `files[0].name` and resets the input. The JSON proxy (`app/api/proxy/[...path]/route.ts`) reads `request.text()` and forces `Content-Type: application/json`, so it cannot carry multipart.
- Backend route tests mock the DB (`MagicMock` + `AsyncMock`); there is no real-DB harness.

### Target State
- `Activity` table + `POST /api/activities/import` + `DELETE /api/activities`.
- Pure, unit-testable modules: CSV parser/validator, import planner (coverage, reach-back, frozen past, tail replace), `compute_positions`.
- Thin DB layer applies the planner's result in one transaction, running the integrity checks on the projected ledger before commit.
- Nav CSV input POSTs the file and renders summary / coverage / rejection detail.

## Impact & Risk

### Files Changed
- **`backend/app/models/activity.py`** (new) — `Activity` model.
- **`backend/app/models/__init__.py`** — export `Activity`.
- **`backend/alembic/versions/0018_activities.py`** (new) — table + indexes.
- **`backend/app/services/wealthsimple_csv.py`** (new) — header-driven parse, type mapping, per-row validation.
- **`backend/app/services/ledger_import.py`** (new) — pure `plan_import` (coverage, reach-back, frozen/tail/prepend split).
- **`backend/app/services/positions.py`** (new) — `compute_positions`, integrity checks.
- **`backend/app/schemas/activity.py`** (new) — response/error models.
- **`backend/app/api/activities.py`** (new) — import + reset routes.
- **`backend/app/main.py`** — register router.
- **`backend/tests/...`** (new) — synthetic fixture CSVs + parser/planner/positions/route tests.
- **`frontend/src/app/api/proxy/activities/import/route.ts`** (new) — multipart passthrough.
- **`frontend/src/components/nav.tsx`** — POST the `File`, show result.
- **`.doc/database.md`, `.doc/api.md`, `.doc/issues.md`** — document model/routes; tick #33.

### Dependencies
- **`verify_api_key` / `get_db`** — reused as-is.
- **#19** — consumes `compute_positions`; its `current_price` quote-symbol rule relies on the native currency this issue infers.
- **#31 `RecentActivityCard`** — later reads `Activity` filtered by ticker (trades + dividends).

### New Dependencies
None.

### Breaking Changes
None. The nav CSV input changes from local-only to a network call (intended).
