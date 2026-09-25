"""Merges a freshly-parsed Wealthsimple export into one account's stored
ledger, without ever matching individual rows — Activity rows have no
unique id, and the originally-proposed dedup key collided on real data
(two same-day $0.01 interest rows, see issue #33). Correctness rests
entirely on date ranges instead: a boundary (newest stored date − 7 days)
splits stored history into a frozen past (never touched) and a tail
(wholesale replaced by the file). Pure — no DB, no FastAPI; the route
(app/api/activities.py) reads the stored range, calls plan_import, and
applies the result in one transaction."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.services.ledger_errors import LedgerImportError
from app.services.wealthsimple_csv import LEDGER_TZ, ParsedRow

_TAIL_WINDOW = timedelta(days=7)


def ledger_date(moment: datetime) -> date:
    """Calendar date of `moment` in the ledger's own timezone. A bare
    `.date()` uses whatever tz the datetime happens to carry — Toronto for a
    freshly parsed row, UTC for one read back from Postgres — so the same
    instant (e.g. a 23:41 local deposit) could print as two different days."""
    return moment.astimezone(LEDGER_TZ).date()


def export_from_date(newest: datetime) -> date:
    """The 'next time export from …' date: the same 7-day subtraction
    plan_import will do against this newest row, done on the UTC instant
    (absolute 7 days, as plan_import sees it once the row is stored) and
    shown as a Toronto calendar date."""
    return ledger_date(newest.astimezone(timezone.utc) - _TAIL_WINDOW)


@dataclass(frozen=True)
class ImportPlan:
    to_insert: list[ParsedRow]
    delete_from: datetime | None  # tail boundary to delete from; None = nothing to replace
    skipped: int
    replaced: int  # of to_insert, how many are tail rows (added = len(to_insert) - replaced)


def plan_import(stored_range: tuple[datetime, datetime] | None, rows: list[ParsedRow]) -> ImportPlan:
    """`rows` must be non-empty and sorted by effective_at ascending — both
    already guaranteed by wealthsimple_csv.parse_export, which is the only
    intended caller of this function's input contract.

    `stored_range` is (earliest, newest) effective_at already stored for
    this account, or None on the very first import (nothing to reconcile
    against — every row is new).
    """
    if stored_range is None:
        return ImportPlan(to_insert=list(rows), delete_from=None, skipped=0, replaced=0)

    stored_earliest, stored_newest = stored_range

    # Boundary inclusive on the tail side: a row dated exactly on the
    # boundary is treated as tail (replaced), not frozen. If the stored
    # range is shorter than 7 days, clamping to stored_earliest means the
    # *entire* stored range counts as tail — a short-lived account can't
    # have a "frozen past" shorter than the window itself (challenges.md #2).
    boundary = max(stored_earliest, stored_newest - _TAIL_WINDOW)

    file_earliest = rows[0].effective_at
    file_newest = rows[-1].effective_at

    # The tail is only refreshed by a file that actually reaches the newest
    # stored row (spec: "a file that ends earlier can only prepend older
    # rows"). Anything less would delete stored rows after the file's last
    # row and have nothing to put back — e.g. re-uploading an older export
    # would silently wipe the newer rows. Only a file that reaches the
    # newest row is required to also reach back to the boundary, since it's
    # the one replacing the tail without a hole.
    reaches_newest = file_newest >= stored_newest
    if reaches_newest and file_earliest > boundary:
        raise LedgerImportError(
            "coverage_gap",
            f"Export doesn't reach back far enough — re-export from {ledger_date(boundary)} or earlier",
            re_export_from=boundary,
        )

    to_insert: list[ParsedRow] = []
    skipped = 0
    replaced = 0
    for row in rows:
        if row.effective_at < stored_earliest:
            # Older than anything stored — prepend. Deliberately NOT checked for
            # contiguity with the earliest stored row: a file of only older rows
            # is accepted even if it leaves a gap before it (documented deviation
            # from the spec's "contiguous on the older side" — see review.md #4).
            to_insert.append(row)
        elif row.effective_at < boundary or not reaches_newest:
            # Frozen past — the file's copy is a no-op by design. Also any
            # row landing in the tail of a file that *doesn't* reach the
            # newest stored row: that tail is left exactly as stored.
            skipped += 1
        else:
            to_insert.append(row)
            replaced += 1

    delete_from = boundary if reaches_newest else None
    return ImportPlan(to_insert=to_insert, delete_from=delete_from, skipped=skipped, replaced=replaced)
