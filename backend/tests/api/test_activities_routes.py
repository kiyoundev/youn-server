import io
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.api import activities, positions
from app.core.db import get_db
from app.services.ledger_cache import LedgerCache

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wealthsimple"


def _upload(content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename="export.csv")


def _min_max_result(earliest, newest):
    """Stand-in for select(func.min(...), func.max(...)) — .one()."""
    result = MagicMock()
    result.one.return_value = (earliest, newest)
    return result


def _list_result(values: list):
    """Stand-in for select(Activity)... — .scalars().all()."""
    scalars = MagicMock()
    scalars.all.return_value = values
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _delete_result(rowcount: int):
    result = MagicMock()
    result.rowcount = rowcount
    return result


def _mock_db(side_effect: list) -> MagicMock:
    """`side_effect` lists the results of the route's *data* queries, in
    order. The per-account advisory lock (a SELECT pg_advisory_xact_lock) is
    answered here without consuming one, so those lists stay a description of
    the queries that matter; every statement, lock included, is recorded on
    `db.statements` as (sql text, params) for tests that care about the lock."""
    results = list(side_effect)
    db = MagicMock()
    db.statements = []

    async def execute(statement, params=None):
        db.statements.append((str(statement), params))
        if "pg_advisory_xact_lock" in str(statement):
            return MagicMock()
        return results.pop(0)

    db.execute = AsyncMock(side_effect=execute)
    db.data_calls = lambda: [sql for sql, _ in db.statements if "pg_advisory_xact_lock" not in sql]
    db.add_all = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _ledger() -> MagicMock:
    """Stand-in for the LedgerCache the routes get through Depends (#19). A
    direct call to a handler skips Depends, so the cache has to be passed in."""
    return MagicMock(spec=LedgerCache)


def _csv(*rows: str) -> bytes:
    header = (
        "effective_date,effective_time,settlement_date,account_id,account_type,"
        "activity_type,activity_sub_type,description,direction,symbol,name,"
        "currency,quantity,unit_price,commission,net_cash_amount"
    )
    return ("\n".join([header, *rows]) + "\n").encode()


@pytest.mark.asyncio
async def test_import_first_time_single_account_succeeds():
    content = (FIXTURES / "base.csv").read_bytes()
    # First-ever import: the min/max query finds nothing stored, so there is
    # nothing to keep and no kept-rows query is run at all (and no delete,
    # since plan.delete_from is None).
    db = _mock_db(side_effect=[_min_max_result(None, None)])

    result = await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert len(result.accounts) == 1
    account = result.accounts[0]
    assert account.account_id == "TEST-ACCT-0001"
    assert account.added == 9
    assert account.replaced == 0
    assert account.skipped == 0
    assert "2026-01-05" in account.message

    db.add_all.assert_called_once()
    inserted = db.add_all.call_args[0][0]
    assert len(inserted) == 9
    assert len(db.data_calls()) == 1  # just the min/max — no wasted kept-rows SELECT
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_message_dates_are_toronto_dates_even_when_newest_row_comes_from_the_db():
    # Prepend-only file: nothing in the tail is replaced, so the newest row in
    # the merged ledger is a stored one, read back from Postgres in UTC —
    # 03:41 UTC on Jul 2 is 23:41 Toronto on Jul 1. A bare .date() on it
    # printed Jul 2 and told the user to export from Jun 25 (one day late,
    # so following it could be rejected as a coverage gap).
    stored_earliest = datetime(2026, 6, 20, 13, 0, tzinfo=timezone.utc)
    stored_newest = datetime(2026, 7, 2, 3, 41, 28, tzinfo=timezone.utc)

    def stored_deposit(at):
        return SimpleNamespace(
            effective_at=at, account_id="A", activity_type="MoneyMovement", symbol=None,
            quantity=None, unit_price=None, fx_rate=None, net_cash_amount=1000.0,
        )

    content = _csv("2026-06-01,09:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,500.00,,0.00,500.00")
    db = _mock_db(
        side_effect=[
            _min_max_result(stored_earliest, stored_newest),
            _list_result([stored_deposit(stored_earliest), stored_deposit(stored_newest)]),
        ]
    )

    result = await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    message = result.accounts[0].message
    assert message == "Ledger runs 2026-06-01 \u2192 2026-07-01; next time export from 2026-06-24 or earlier."


@pytest.mark.asyncio
async def test_import_rejects_unknown_activity_type_before_any_db_write():
    content = (FIXTURES / "unknown_type.csv").read_bytes()
    db = _mock_db(side_effect=[])  # parse_export fails before any db.execute

    with pytest.raises(HTTPException) as exc:
        await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "unknown_activity_type"
    db.execute.assert_not_called()
    db.add_all.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_rejects_coverage_gap_before_any_db_write():
    # Same shape as test_ledger_import.py's gap scenario: stored Jan 1-20
    # (boundary = Jan 13), file starts Jan 15 — doesn't reach back far enough.
    content = _csv(
        "2026-01-15,09:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00",
        "2026-01-25,09:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00",
    )
    stored = (
        datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 1, 20, 9, tzinfo=timezone.utc),
    )
    db = _mock_db(side_effect=[_min_max_result(*stored)])  # plan_import raises before the kept query

    with pytest.raises(HTTPException) as exc:
        await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "coverage_gap"
    db.add_all.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_rejects_negative_cash_before_writing():
    # A buy with no prior deposit — compute_positions' integrity gate
    # catches this after plan_import succeeds but before any write.
    content = _csv(
        "2026-01-01,09:00:00,,A,TFSA,Trade,BUY,"
        "\"X - Test: Bought 1.0000 shares\",LONG,X,Test,CAD,1.0000,100.00,0.00,-100.00",
    )
    db = _mock_db(side_effect=[_min_max_result(None, None)])

    with pytest.raises(HTTPException) as exc:
        await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "negative_cash"
    db.add_all.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_handles_multiple_accounts_in_one_file():
    content = _csv(
        "2026-01-01,09:00:00,,ACCT-A,TFSA,MoneyMovement,EFT,dep,,,,CAD,500.00,,0.00,500.00",
        "2026-01-02,09:00:00,,ACCT-B,TFSA,MoneyMovement,EFT,dep,,,,CAD,700.00,,0.00,700.00",
    )
    # Two accounts, both first-time imports: min/max + kept-empty, per account,
    # in the order each account's first row appears in the sorted file (A then B).
    db = _mock_db(
        side_effect=[
            _min_max_result(None, None),  # ACCT-A
            _min_max_result(None, None),  # ACCT-B
        ]
    )

    result = await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    ids = {a.account_id for a in result.accounts}
    assert ids == {"ACCT-A", "ACCT-B"}
    assert all(a.added == 1 for a in result.accounts)
    db.commit.assert_awaited_once()  # one transaction, not one per account


@pytest.mark.asyncio
async def test_reset_ledger_deletes_and_returns_count():
    db = _mock_db(side_effect=[_delete_result(4)])

    result = await activities.reset_ledger(account_id="TEST-ACCT-0001", db=db, ledger=_ledger())

    assert result.account_id == "TEST-ACCT-0001"
    assert result.deleted == 4
    db.commit.assert_awaited_once()


def _stored_deposit(at):
    return SimpleNamespace(
        effective_at=at, account_id="A", activity_type="MoneyMovement", symbol=None,
        quantity=None, unit_price=None, fx_rate=None, net_cash_amount=1000.0,
    )


_JAN_1 = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
_JAN_20 = datetime(2026, 1, 20, 9, tzinfo=timezone.utc)  # stored newest; the tail boundary is Jan 13
# Local Toronto times chosen so they land on those UTC instants (EST is UTC-5).
_ROW_JAN_1 = "2026-01-01,04:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00"
_ROW_JAN_15 = "2026-01-15,04:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00"
_ROW_JAN_16 = "2026-01-16,04:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00"
_ROW_JAN_20 = "2026-01-20,04:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00"


@pytest.mark.asyncio
async def test_import_refreshes_the_tail_when_the_file_reaches_the_newest_row():
    # The write path a real re-import takes: min/max, the kept rows, then the
    # DELETE of the tail — three executes — and only the tail's rows inserted.
    db = _mock_db(
        side_effect=[
            _min_max_result(_JAN_1, _JAN_20),
            _list_result([_stored_deposit(_JAN_1)]),  # what stays: rows before the boundary
            _delete_result(2),
        ]
    )

    result = await activities.import_activities(
        file=_upload(_csv(_ROW_JAN_1, _ROW_JAN_15, _ROW_JAN_20)), db=db, ledger=_ledger()
    )

    account = result.accounts[0]
    assert (account.added, account.replaced, account.skipped) == (0, 2, 1)
    assert len(db.data_calls()) == 3  # min/max, kept rows, then the DELETE
    assert len(db.add_all.call_args[0][0]) == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_of_a_file_ending_before_the_newest_row_deletes_nothing():
    # Regression: this used to run the DELETE and lose the rows after the
    # file's last row. Two executes only (min/max + kept) — no DELETE.
    db = _mock_db(
        side_effect=[
            _min_max_result(_JAN_1, _JAN_20),
            _list_result([_stored_deposit(_JAN_1), _stored_deposit(_JAN_20)]),  # everything stays
        ]
    )

    result = await activities.import_activities(file=_upload(_csv(_ROW_JAN_1, _ROW_JAN_16)), db=db, ledger=_ledger())

    account = result.accounts[0]
    assert (account.added, account.replaced, account.skipped) == (0, 0, 2)
    assert len(db.data_calls()) == 2  # min/max + kept — no DELETE
    assert db.add_all.call_args[0][0] == []
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_is_all_or_nothing_across_accounts():
    # ACCT-A is valid and gets staged; ACCT-B then fails its integrity check
    # (a buy with no funding). The "one transaction" guarantee: A's staged
    # rows must not be committed.
    content = _csv(
        "2026-01-01,09:00:00,,ACCT-A,TFSA,MoneyMovement,EFT,dep,,,,CAD,500.00,,0.00,500.00",
        "2026-01-02,09:00:00,,ACCT-B,TFSA,Trade,BUY,\"X - Test: Bought 1.0000 shares\","
        "LONG,X,Test,CAD,1.0000,100.00,0.00,-100.00",
    )
    db = _mock_db(
        side_effect=[
            _min_max_result(None, None),  # ACCT-A
            _min_max_result(None, None),  # ACCT-B
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert exc.value.detail["code"] == "negative_cash"
    db.add_all.assert_called_once()  # A really was staged...
    db.commit.assert_not_awaited()  # ...and never committed
    db.rollback.assert_awaited_once()


# ---- through the real response layer ----
# The tests above call the handler directly, so they only ever see the
# HTTPException object — never how it serializes. A datetime inside
# `detail` (coverage_gap's re_export_from, negative_cash's date) passed
# every one of them while returning a bare 500 over real HTTP.


def _client(db: MagicMock, ledger: MagicMock | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(activities.router)
    ledger = ledger if ledger is not None else _ledger()

    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    # No lifespan here, so app.state.ledger_cache doesn't exist; FastAPI
    # resolves this dependency before the handler runs, even for a request
    # that is about to be rejected.
    app.dependency_overrides[positions.get_ledger_cache] = lambda: ledger
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, content: bytes):
    return client.post("/api/activities/import", files={"file": ("export.csv", content, "text/csv")})


def test_coverage_gap_is_a_422_json_response_not_a_500():
    content = _csv(
        "2026-01-15,09:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00",
        "2026-01-25,09:00:00,,A,TFSA,MoneyMovement,EFT,dep,,,,CAD,100.00,,0.00,100.00",
    )
    stored = (datetime(2026, 1, 1, 9, tzinfo=timezone.utc), datetime(2026, 1, 20, 9, tzinfo=timezone.utc))
    db = _mock_db(side_effect=[_min_max_result(*stored)])

    response = _post(_client(db), content)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "coverage_gap"
    assert detail["re_export_from"].startswith("2026-01-13")


def test_negative_cash_is_a_422_json_response_not_a_500():
    content = _csv(
        "2026-01-01,09:00:00,,A,TFSA,Trade,BUY,"
        "\"X - Test: Bought 1.0000 shares\",LONG,X,Test,CAD,1.0000,100.00,0.00,-100.00",
    )
    db = _mock_db(side_effect=[_min_max_result(None, None)])

    response = _post(_client(db), content)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "negative_cash"
    assert detail["date"].startswith("2026-01-01")


def test_non_utf8_upload_is_a_422_invalid_file():
    db = _mock_db(side_effect=[])

    response = _post(_client(db), b"\xff\xfe\x00 not utf-8 at all")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_file"
    db.execute.assert_not_called()


# ---- per-account advisory lock ----
# Two overlapping imports would both plan against the same stored range and
# double-insert (no unique constraint, by design). The lock serializes them.


def _lock_accounts(db: MagicMock) -> list[str]:
    return [params["account_id"] for sql, params in db.statements if "pg_advisory_xact_lock" in sql]


@pytest.mark.asyncio
async def test_import_takes_the_account_lock_before_reading_anything():
    content = (FIXTURES / "base.csv").read_bytes()
    db = _mock_db(side_effect=[_min_max_result(None, None)])

    await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert "pg_advisory_xact_lock" in db.statements[0][0]  # first statement, ahead of the range query
    assert _lock_accounts(db) == ["TEST-ACCT-0001"]


@pytest.mark.asyncio
async def test_multi_account_import_locks_every_account_up_front_in_sorted_order():
    # Sorted, and all before any data query: two concurrent multi-account
    # imports taking locks in file order could each hold one and wait on the
    # other. ACCT-B's row comes first in the file; the lock order must not.
    content = _csv(
        "2026-01-01,09:00:00,,ACCT-B,TFSA,MoneyMovement,EFT,dep,,,,CAD,700.00,,0.00,700.00",
        "2026-01-02,09:00:00,,ACCT-A,TFSA,MoneyMovement,EFT,dep,,,,CAD,500.00,,0.00,500.00",
    )
    db = _mock_db(
        side_effect=[
            _min_max_result(None, None),
            _min_max_result(None, None),
        ]
    )

    await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    assert _lock_accounts(db) == ["ACCT-A", "ACCT-B"]
    first_data_query = next(i for i, (sql, _) in enumerate(db.statements) if "pg_advisory_xact_lock" not in sql)
    assert first_data_query == 2  # both locks precede it


@pytest.mark.asyncio
async def test_a_rejected_file_never_takes_a_lock():
    db = _mock_db(side_effect=[])

    with pytest.raises(HTTPException):
        await activities.import_activities(file=_upload((FIXTURES / "unknown_type.csv").read_bytes()), db=db, ledger=_ledger())

    assert db.statements == []  # parse failed first — nothing touched the DB


@pytest.mark.asyncio
async def test_reset_takes_the_same_account_lock_before_deleting():
    db = _mock_db(side_effect=[_delete_result(1)])

    await activities.reset_ledger(account_id="ACCT-A", db=db, ledger=_ledger())

    assert "pg_advisory_xact_lock" in db.statements[0][0]
    assert _lock_accounts(db) == ["ACCT-A"]
    assert "DELETE" in db.statements[1][0].upper()


# ---- upload size cap ----


def test_oversized_upload_is_a_413_and_touches_nothing():
    db = _mock_db(side_effect=[])
    too_big = b"x" * (activities._MAX_UPLOAD_BYTES + 1)

    response = _post(_client(db), too_big)

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"
    assert db.statements == []  # rejected before parsing, before any lock or query


def test_an_upload_exactly_at_the_cap_is_still_read():
    # Not rejected for size: it fails later, as a CSV, with the file's own error.
    db = _mock_db(side_effect=[])
    at_cap = b"x" * activities._MAX_UPLOAD_BYTES

    response = _post(_client(db), at_cap)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] != "file_too_large"


# ---- LedgerCache invalidation (#19) ----
# The cache holds a copy of what the ledger adds up to. Only these two routes
# change the ledger, so only they can say the copy is stale. It has to be after
# the commit: a read that starts between invalidate() and the commit loads the
# old rows and stores them, and nothing clears them again.

_NEGATIVE_CASH = _csv(
    "2026-01-01,09:00:00,,A,TFSA,Trade,BUY,"
    "\"X - Test: Bought 1.0000 shares\",LONG,X,Test,CAD,1.0000,100.00,0.00,-100.00",
)


def _record_order(db: MagicMock, ledger: MagicMock) -> list[str]:
    """The order in which the route committed and invalidated."""
    order: list[str] = []
    db.commit.side_effect = lambda: order.append("commit")
    ledger.invalidate.side_effect = lambda: order.append("invalidate")
    return order


@pytest.mark.asyncio
async def test_import_invalidates_the_ledger_cache_after_the_commit():
    db = _mock_db(side_effect=[_min_max_result(None, None)])
    ledger = _ledger()
    order = _record_order(db, ledger)

    await activities.import_activities(file=_upload((FIXTURES / "base.csv").read_bytes()), db=db, ledger=ledger)

    assert order == ["commit", "invalidate"]


@pytest.mark.asyncio
async def test_reset_invalidates_the_ledger_cache_after_the_commit():
    db = _mock_db(side_effect=[_delete_result(4)])
    ledger = _ledger()
    order = _record_order(db, ledger)

    await activities.reset_ledger(account_id="ACCT-A", db=db, ledger=ledger)

    assert order == ["commit", "invalidate"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [(FIXTURES / "unknown_type.csv").read_bytes(), _NEGATIVE_CASH],
    ids=["rejected_while_parsing", "rejected_by_the_integrity_check"],
)
async def test_a_rejected_import_does_not_invalidate_the_ledger_cache(content):
    # Rolled back, so the ledger is exactly what the cache already holds.
    db = _mock_db(side_effect=[_min_max_result(None, None)])
    ledger = _ledger()

    with pytest.raises(HTTPException) as exc:
        await activities.import_activities(file=_upload(content), db=db, ledger=ledger)

    assert exc.value.status_code == 422
    ledger.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_commit_does_not_invalidate_the_import():
    db = _mock_db(side_effect=[_min_max_result(None, None)])
    db.commit.side_effect = RuntimeError("connection lost")
    ledger = _ledger()

    with pytest.raises(RuntimeError):
        await activities.import_activities(file=_upload((FIXTURES / "base.csv").read_bytes()), db=db, ledger=ledger)

    ledger.invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_commit_does_not_invalidate_the_reset():
    db = _mock_db(side_effect=[_delete_result(1)])
    db.commit.side_effect = RuntimeError("connection lost")
    ledger = _ledger()

    with pytest.raises(RuntimeError):
        await activities.reset_ledger(account_id="ACCT-A", db=db, ledger=ledger)

    ledger.invalidate.assert_not_called()


def test_both_routes_invalidate_the_cache_they_are_given_through_dependencies():
    # Through the real request path: proves the routes ask for the cache via
    # positions.get_ledger_cache, so the one on app.state is the one cleared.
    db = _mock_db(side_effect=[_min_max_result(None, None), _delete_result(2)])
    ledger = _ledger()
    client = _client(db, ledger)

    assert _post(client, (FIXTURES / "base.csv").read_bytes()).status_code == 200
    assert ledger.invalidate.call_count == 1

    assert client.delete("/api/activities", params={"account_id": "TEST-ACCT-0001"}).status_code == 200
    assert ledger.invalidate.call_count == 2


# ---- contracts that ran but weren't asserted ----


@pytest.mark.asyncio
async def test_import_response_carries_the_positions_warning():
    # Non-fatal: a ledger whose first row is a dividend (positive cash, so no
    # negative_cash) rather than a funding deposit. It must reach the caller.
    content = _csv("2026-01-01,09:00:00,,A,TFSA,Dividend,-,\"X - Test: Cash dividend\",,X,Test,CAD,5.00,,0.00,5.00")
    db = _mock_db(side_effect=[_min_max_result(None, None)])

    result = await activities.import_activities(file=_upload(content), db=db, ledger=_ledger())

    warnings = result.accounts[0].warnings
    assert len(warnings) == 1
    assert "funding deposit" in warnings[0]
    db.commit.assert_awaited_once()  # a warning doesn't block the import


def test_parsed_row_and_activity_have_the_same_columns():
    # The route builds Activity(**asdict(row)). An extra ParsedRow field fails
    # loudly; an Activity column with no ParsedRow counterpart would not — the
    # mocked-DB tests never insert. id and created_at are database-assigned.
    from dataclasses import fields

    from app.models.activity import Activity
    from app.services.wealthsimple_csv import ParsedRow

    parsed = {f.name for f in fields(ParsedRow)}
    stored = {c.name for c in Activity.__table__.columns} - {"id", "created_at"}
    assert parsed == stored
