# Issue #33: Schema & API Contract

## Database — `activities` (migration `0018`)

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `effective_at` | timestamptz NOT NULL | `effective_date` + `effective_time`, interpreted as `America/Toronto` |
| `settlement_date` | date NULL | populated on trades only |
| `account_id` | str NOT NULL | every query is keyed by it |
| `account_type` | str NOT NULL | |
| `activity_type` | str NOT NULL | `Trade` / `MoneyMovement` / `Interest` / `Dividend` / `Tax` |
| `activity_sub_type` | str NOT NULL | `BUY`, `EFT`, `E_TRFIN`, `NRT`, `-` … |
| `description` | str NOT NULL | |
| `direction` | str NULL | `LONG` on buys; sell string unconfirmed |
| `symbol` | str NULL | |
| `name` | str NULL | |
| `currency` | str NOT NULL | always CAD so far |
| `quantity` | float NULL | **shares, `Trade` rows only** (overloaded column on other types) |
| `unit_price` | float NULL | CAD |
| `fx_rate` | float NULL | parsed from `FX Rate: x` in description |
| `commission` | float NOT NULL default 0 | stored, not used in cost or validated — real exports confirm it's always `0` (decided 2026-09-22) |
| `net_cash_amount` | float NOT NULL | signed CAD; drives cost and cash |
| `created_at` | timestamptz NOT NULL | server default now |

Indexes: `(account_id, effective_at)` (ordering + coverage). **No unique constraint** — rows have no id and same-day rows legitimately look alike.

`downgrade()` drops the table.

## API Routes

Both registered in `main.py` with `Depends(verify_api_key)`.

### `POST /api/activities/import`
- **Handler:** `backend/app/api/activities.py`
- **Request:** `multipart/form-data`, one `UploadFile` field `file` (`.csv`).
- **Response 200:** `ImportResult`
  - `accounts: list[AccountImportResult]`, each: `account_id`, `added`, `replaced`, `skipped`, `coverage: {earliest, newest}`, `message` ("Ledger runs A → B; next time export from B − 7 days or earlier."), `warnings: list[str]` (e.g. history doesn't start with a funding deposit).
- **Error cases** (all leave the DB untouched; every `LedgerImportError` is a **422** — none are 400 — with body `{"detail": {"code", "message", ...extras}}`; datetimes in extras are ISO strings via `jsonable_encoder`, without which they 500):
  - `422 invalid_file` — upload isn't valid UTF-8.
  - `422 empty_file` — no data rows.
  - `422 malformed_row` — unparseable number/date on a row; extras `line`, `field`.
  - `422 missing_columns` — required header absent (lists which).
  - `422 missing_effective_date` — a row has blank `effective_date`/`effective_time`; not derived from `settlement_date`.
  - `422 unsupported_currency` — a row's `currency` column isn't `CAD` (this is a CAD account; every row is stamped CAD even on a USD stock trade — distinct from the holding's *native* currency, which is inferred from the FX text, not this column).
  - `422 unknown_activity_type` — lists `activity_type`, `activity_sub_type`, `direction`, count, one example description, copy-pasteable.
  - `422 coverage_gap` — export doesn't reach back far enough; includes `re_export_from` date.
  - `422 negative_holdings` / `negative_cash` / `mixed_native_currency` — projected ledger fails the integrity checks; names the symbol/date.

### `DELETE /api/activities`
- **Handler:** `backend/app/api/activities.py`
- **Request:** query `account_id` (required).
- **Response 200:** `{"account_id": str, "deleted": int}`.
- **Error cases:** `422` if `account_id` missing; deleting an account with no rows returns `deleted: 0`.
- Backend-only (no frontend caller) — decided 2026-09-21.

## Python interfaces
```python
@dataclass(frozen=True)
class ParsedRow:            # one validated CSV row, ready to persist
    effective_at: datetime
    settlement_date: date | None
    account_id: str
    ...                     # mirrors Activity columns

@dataclass(frozen=True)
class ImportPlan:           # per account, pure output of plan_import
    to_insert: list[ParsedRow]
    delete_from: datetime | None   # tail start; None = nothing to replace
    skipped: int
    replaced: int

class Holding:
    account_id: str
    symbol: str
    shares: float
    native_currency: Literal["CAD", "USD"]
    avg_cost_native: float
    avg_cost_cad: float

class ActivityLike(Protocol):  # structural — ParsedRow and the future Activity
    effective_at: datetime     # model both satisfy this with no inheritance
    account_id: str
    activity_type: str
    symbol: str | None
    quantity: float | None
    unit_price: float | None
    fx_rate: float | None
    net_cash_amount: float

def parse_export(content: bytes) -> list[ParsedRow]: ...
def plan_import(stored_range: tuple[datetime, datetime] | None, rows: list[ParsedRow]) -> ImportPlan: ...
def compute_positions(activities: Sequence[ActivityLike]) -> tuple[list[Holding], float, list[str]]: ...
    # holdings, cash, warnings — corrected 2026-09-22: warnings (e.g. "history
    # doesn't start with a funding deposit") can only be computed inside this
    # function, and the route's ImportResult needs to surface them, so the
    # original 2-tuple sketch was insufficient.
```

## Frontend contract
- `POST /api/proxy/activities/import` (dedicated route) — forwards raw body + `Content-Type` (with boundary) and `X-API-Key`; relays status/body unchanged.
