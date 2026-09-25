from datetime import date, datetime, timezone

import pytest

from app.services.ledger_errors import LedgerImportError
from app.services.ledger_import import export_from_date, ledger_date, plan_import
from app.services.wealthsimple_csv import ParsedRow


def _row(year: int, month: int, day: int, hour: int = 9, **overrides) -> ParsedRow:
    """A minimal, otherwise-irrelevant row dated (year, month, day, hour) —
    plan_import only ever looks at .effective_at, so every other field is a
    fixed placeholder unless a test overrides it (e.g. description, to
    build the same-day-but-different-text case)."""
    base = dict(
        effective_at=datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc),
        settlement_date=None,
        account_id="TEST-ACCT-0001",
        account_type="NON_REGISTERED",
        activity_type="MoneyMovement",
        activity_sub_type="EFT",
        description=f"row {year}-{month:02d}-{day:02d}",
        direction=None,
        symbol=None,
        name=None,
        currency="CAD",
        quantity=None,
        unit_price=None,
        fx_rate=None,
        commission=0.0,
        net_cash_amount=1.0,
    )
    base.update(overrides)
    return ParsedRow(**base)


def _days(*days: int, month: int = 1, year: int = 2026) -> list[ParsedRow]:
    return [_row(year, month, d) for d in days]


# Stored range shared by most tests: Jan 1 -> Jan 20, boundary = Jan 13 (20 - 7).
_STORED = (
    datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
    datetime(2026, 1, 20, 9, tzinfo=timezone.utc),
)
_BOUNDARY_DAY = 13


def test_first_import_inserts_everything():
    rows = _days(1, 2, 3)
    plan = plan_import(None, rows)
    assert plan.to_insert == rows
    assert plan.delete_from is None
    assert plan.skipped == 0
    assert plan.replaced == 0


def test_identical_reimport_skips_frozen_replaces_tail():
    rows = _days(*range(1, 21))  # same span as _STORED
    plan = plan_import(_STORED, rows)
    assert plan.skipped == 12  # days 1-12, before the boundary
    assert plan.replaced == 8  # days 13-20
    assert len(plan.to_insert) == 8
    assert plan.delete_from.day == _BOUNDARY_DAY


def test_overlapping_extension_replaces_tail_and_adds_new_days():
    rows = _days(*range(10, 26))  # reaches back to 10 (<= boundary 13), extends to 25
    plan = plan_import(_STORED, rows)
    assert plan.skipped == 3  # days 10-12
    assert plan.replaced == 13  # days 13-25
    assert plan.delete_from.day == _BOUNDARY_DAY


def test_prepend_only_older_file_does_not_touch_tail():
    rows = [_row(2025, 12, d) for d in range(25, 32)]  # entirely before stored_earliest
    plan = plan_import(_STORED, rows)
    assert len(plan.to_insert) == 7
    assert plan.skipped == 0
    assert plan.replaced == 0
    assert plan.delete_from is None


def test_gap_is_rejected_with_reexport_date():
    rows = _days(*range(15, 26))  # starts after the boundary (13), reaches past newest
    with pytest.raises(LedgerImportError) as exc:
        plan_import(_STORED, rows)
    assert exc.value.code == "coverage_gap"
    assert exc.value.details["re_export_from"].day == _BOUNDARY_DAY


def test_file_ending_before_boundary_is_not_rejected_just_skipped():
    rows = _days(5, 6, 7, 8, 9, 10)  # newest (10) is still before the boundary (13)
    plan = plan_import(_STORED, rows)  # must not raise
    assert plan.to_insert == []
    assert plan.skipped == 6
    assert plan.delete_from is None


def test_short_stored_range_treats_whole_range_as_tail():
    short_stored = (
        datetime(2026, 1, 10, 9, tzinfo=timezone.utc),
        datetime(2026, 1, 12, 9, tzinfo=timezone.utc),
    )  # 2-day span, shorter than the 7-day window
    rows = _days(10, 11, 12, 13)
    plan = plan_import(short_stored, rows)
    assert plan.skipped == 0
    assert plan.replaced == 4
    assert plan.delete_from.day == 10  # clamped to stored_earliest, not day 5


def test_boundary_day_itself_counts_as_tail_not_frozen():
    # A file whose earliest row lands exactly on the boundary must pass the
    # reach-back check (not "> boundary") and that row must be replaced,
    # not skipped — boundary is inclusive on the tail side (documented in
    # ledger_import.py).
    rows = _days(_BOUNDARY_DAY, 20)  # reaches the newest stored row (day 20), so the tail is refreshed
    plan = plan_import(_STORED, rows)
    assert plan.skipped == 0
    assert plan.replaced == 2


def test_row_on_earliest_stored_date_is_frozen_not_prepended():
    rows = _days(1, 20)  # day 1 == stored_earliest exactly
    plan = plan_import(_STORED, rows)
    assert plan.skipped == 1  # day 1 is frozen, not treated as "older than stored"
    assert plan.replaced == 1  # day 20


def test_same_day_lookalike_rows_both_survive_an_import_and_a_reimport():
    # The case the original dedup-key proposal collided on: two rows, same
    # day, same amount, different description only. plan_import never
    # compares content, so nothing here can merge or drop either one.
    rows = _days(*range(10, 21)) + [
        _row(2026, 1, 20, 12, net_cash_amount=0.01, description="Stock lending interest: USD source"),
        _row(2026, 1, 20, 12, net_cash_amount=0.01, description="Stock lending interest: CAD source"),
    ]
    rows.sort(key=lambda r: r.effective_at)

    first = plan_import(_STORED, rows)
    assert first.replaced == len(rows) - 3  # days 10-12 skipped, both cent rows included in the tail
    assert sum(1 for r in first.to_insert if r.net_cash_amount == 0.01) == 2

    # Re-import the identical file — both cent rows still in the tail, still both present.
    second = plan_import(_STORED, rows)
    assert sum(1 for r in second.to_insert if r.net_cash_amount == 0.01) == 2


# ---- dates shown to the user are Toronto dates, whatever tz the datetime carries ----
# 23:41 Toronto on Jul 1 is 03:41 UTC on Jul 2 — the same instant, two calendar days.
_LATE_EVENING_UTC = datetime(2026, 7, 2, 3, 41, 28, tzinfo=timezone.utc)


def test_ledger_date_is_the_toronto_calendar_date_not_the_utc_one():
    assert ledger_date(_LATE_EVENING_UTC) == date(2026, 7, 1)


def test_export_from_date_is_seven_days_before_the_toronto_date():
    assert export_from_date(_LATE_EVENING_UTC) == date(2026, 6, 24)  # not 06-25


def test_coverage_gap_message_names_the_toronto_date():
    stored = (datetime(2026, 6, 1, 9, tzinfo=timezone.utc), _LATE_EVENING_UTC)  # boundary = Jun 25 03:41 UTC
    rows = [_row(2026, 6, 27), _row(2026, 7, 5)]  # starts after the boundary, reaches past newest
    with pytest.raises(LedgerImportError) as exc:
        plan_import(stored, rows)
    assert "2026-06-24" in exc.value.message
    assert "2026-06-25" not in exc.value.message


# ---- a file that ends before the newest stored row must never delete anything ----
# Spec: "the tail is refreshed only when the file actually reaches the newest
# stored date; a file that ends earlier can only prepend older rows." The first
# version keyed on the boundary instead, so re-uploading an older export
# (ending between the boundary and the newest row) deleted the stored rows
# after its last row and had nothing to put back.


def test_file_ending_between_boundary_and_newest_leaves_the_tail_untouched():
    rows = _days(*range(1, 17))  # days 1-16; boundary is 13, newest stored row is day 20
    plan = plan_import(_STORED, rows)
    assert plan.delete_from is None  # nothing deleted, so days 17-20 survive
    assert plan.to_insert == []
    assert plan.replaced == 0
    assert plan.skipped == 16


def test_file_ending_before_newest_still_prepends_older_rows():
    rows = [_row(2025, 12, 30), _row(2025, 12, 31), *_days(1, 2, 16)]  # ends day 16 < newest day 20
    plan = plan_import(_STORED, rows)
    assert plan.delete_from is None
    assert [r.effective_at.day for r in plan.to_insert] == [30, 31]  # only the older rows
    assert plan.skipped == 3


def test_file_ending_before_newest_is_never_rejected_for_a_gap():
    # Starts after the boundary but doesn't reach the newest row: it isn't
    # replacing the tail, so it can't leave a hole in it — nothing to reject.
    plan = plan_import(_STORED, _days(15, 16))
    assert plan.delete_from is None
    assert plan.skipped == 2
