"""Wealthsimple activity import (issue #33). Turns an uploaded CSV export
into a durable Activity ledger and derives holdings from it — see
services/wealthsimple_csv.py (parse), services/ledger_import.py (merge),
services/positions.py (integrity check). No read endpoints here — #19
owns those, against the committed Activity rows."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_ledger_cache
from app.models.activity import Activity
from app.schemas.activity import AccountCoverage, AccountImportResult, ImportResult, ResetResult
from app.services.ledger_cache import LedgerCache
from app.services.ledger_errors import LedgerImportError
from app.services.ledger_import import export_from_date, ledger_date, plan_import
from app.services.positions import compute_positions
from app.services.wealthsimple_csv import ParsedRow, parse_export

router = APIRouter()

# A real export is tens of KB (hundreds of rows). This only exists so a wrong
# file picked by mistake can't be read whole into memory. The frontend proxy
# route (api/proxy/activities/import/route.ts) checks the same number.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# First half of the two-int advisory-lock key (the second is a hash of the
# account_id) — the issue number, so it can't collide with any other
# advisory lock the app might take later.
_ADVISORY_LOCK_NAMESPACE = 33


async def _lock_account(db: AsyncSession, account_id: str) -> None:
    """Serializes writes to one account's ledger. An import plans against the
    stored range it reads, then deletes and inserts; two overlapping imports
    (or an import racing a reset) would both plan against the same stored
    state and double-insert — and there's no unique constraint to catch it,
    by design (the export has no row id). Transaction-scoped: released
    automatically at commit or rollback, so no path can leak it."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, hashtext(:account_id))"),
        {"ns": _ADVISORY_LOCK_NAMESPACE, "account_id": account_id},
    )


def _group_by_account(rows: list[ParsedRow]) -> dict[str, list[ParsedRow]]:
    """Preserves each account's chronological order (rows is already sorted
    by effective_at) — deliberately not itertools.groupby, which only
    groups consecutive runs and would silently split an account's rows
    into multiple groups if another account's rows interleave by date."""
    by_account: dict[str, list[ParsedRow]] = {}
    for row in rows:
        by_account.setdefault(row.account_id, []).append(row)
    return by_account


async def _import_one_account(account_id: str, account_rows: list[ParsedRow], db: AsyncSession) -> AccountImportResult:
    stored_range_row = await db.execute(
        select(func.min(Activity.effective_at), func.max(Activity.effective_at)).where(Activity.account_id == account_id)
    )
    earliest, newest = stored_range_row.one()
    stored_range = (earliest, newest) if earliest is not None else None

    plan = plan_import(stored_range, account_rows)  # raises LedgerImportError on a coverage gap

    if stored_range is None:
        kept = []  # first import for this account — nothing stored to keep
    else:
        kept_query = select(Activity).where(Activity.account_id == account_id)
        if plan.delete_from is not None:
            kept_query = kept_query.where(Activity.effective_at < plan.delete_from)
        kept = (await db.execute(kept_query)).scalars().all()

    merged = list(kept) + plan.to_insert
    # Integrity-check gate — nothing below this point writes anything if
    # compute_positions raises (negative shares/cash, mixed FX presence).
    _holdings, _cash, warnings = compute_positions(merged)

    if plan.delete_from is not None:
        await db.execute(delete(Activity).where(Activity.account_id == account_id, Activity.effective_at >= plan.delete_from))
    db.add_all([Activity(**asdict(row)) for row in plan.to_insert])

    all_dates = [a.effective_at for a in merged]
    new_earliest, new_newest = min(all_dates), max(all_dates)

    return AccountImportResult(
        account_id=account_id,
        added=len(plan.to_insert) - plan.replaced,
        replaced=plan.replaced,
        skipped=plan.skipped,
        coverage=AccountCoverage(earliest=new_earliest, newest=new_newest),
        message=(
            f"Ledger runs {ledger_date(new_earliest)} → {ledger_date(new_newest)}; "
            f"next time export from {export_from_date(new_newest)} or earlier."
        ),
        warnings=warnings,
    )


@router.post(
    "/api/activities/import",
    response_model=ImportResult,
    summary="Import a Wealthsimple activities export",
    description=(
        "Multipart CSV upload. Parses, validates, merges into each account's "
        "stored ledger (coverage/reach-back/frozen-past — see "
        "services/ledger_import.py), and derives positions as an integrity "
        "check before committing. One transaction across every account in "
        "the file — either all of it lands, or none of it does."
    ),
)
async def import_activities(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ledger: LedgerCache = Depends(get_ledger_cache),
) -> ImportResult:
    # One byte past the cap is enough to tell it's over, without reading the rest.
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "message": f"File is larger than {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB — a Wealthsimple "
                "export is far smaller than that, so this probably isn't one",
            },
        )

    try:
        rows = parse_export(content)
        by_account = _group_by_account(rows)

        # All locks up front, in a fixed order, before anything is read — two
        # concurrent multi-account imports taking them in file order could
        # otherwise each hold one and wait on the other (deadlock).
        for account_id in sorted(by_account):
            await _lock_account(db, account_id)

        results = [await _import_one_account(account_id, account_rows, db) for account_id, account_rows in by_account.items()]
    except LedgerImportError as e:
        await db.rollback()
        # jsonable_encoder: details can carry datetimes (coverage_gap's
        # re_export_from, negative_cash/negative_holdings' date), which
        # Starlette's JSONResponse can't serialize on its own — without
        # this the client gets a bare 500 instead of the structured 422.
        raise HTTPException(
            status_code=422,
            detail=jsonable_encoder({"code": e.code, "message": e.message, **e.details}),
        ) from e

    await db.commit()
    # After the commit, never before: a read that starts between the two would
    # load the old rows and store them (#19 LedgerCache).
    ledger.invalidate()
    return ImportResult(accounts=results)


@router.delete(
    "/api/activities",
    response_model=ResetResult,
    summary="Reset an account's ledger",
    description=(
        "Deletes every Activity row for one account_id — the recovery path "
        "for the frozen-past 'known limit' (a correction to an already-"
        "frozen row needs a full re-import). Backend-only, no frontend "
        "caller (decided 2026-09-21) — rare and destructive enough that a "
        "curl call with the API key is the right amount of friction."
    ),
)
async def reset_ledger(
    account_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    ledger: LedgerCache = Depends(get_ledger_cache),
) -> ResetResult:
    await _lock_account(db, account_id)
    result = await db.execute(delete(Activity).where(Activity.account_id == account_id))
    await db.commit()
    ledger.invalidate()  # after the commit, as in import_activities
    return ResetResult(account_id=account_id, deleted=result.rowcount or 0)
