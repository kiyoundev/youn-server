from pathlib import Path

import pytest

from app.services.ledger_errors import LedgerImportError
from app.services.wealthsimple_csv import (
    _REQUIRED_COLUMNS,
    _check_allowlist,
    _parse_row,
    _read_rows,
    parse_export,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wealthsimple"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _read_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _rows(name: str) -> list[dict]:
    return _read_rows(_read(name))


def _parsed(name: str) -> list:
    raw_rows = _rows(name)
    return [_parse_row(r, i + 2) for i, r in enumerate(raw_rows)]


def _row(**overrides) -> dict:
    """A single raw CSV row dict with every required column present,
    defaulting to a plain CAD deposit — override just the fields a test
    cares about. _parse_row indexes every _REQUIRED_COLUMNS key directly
    (no .get()), so a hand-built row needs all of them present."""
    base = {key: "" for key in _REQUIRED_COLUMNS}
    base.update(
        effective_date="2026-01-01",
        effective_time="09:30:00",
        settlement_date="",
        account_id="TEST-ACCT-0001",
        account_type="NON_REGISTERED",
        activity_type="MoneyMovement",
        activity_sub_type="EFT",
        description="Electronic funds transfer in",
        currency="CAD",
        net_cash_amount="1000.00",
    )
    base.update(overrides)
    return base


# ---- _read_rows ----


def test_read_rows_base_csv_has_nine_rows():
    assert len(_rows("base.csv")) == 9


def test_read_rows_missing_columns_lists_every_absent_name():
    text = "effective_date,effective_time\n2026-01-01,09:30:00\n"
    with pytest.raises(LedgerImportError) as exc:
        _read_rows(text)
    assert exc.value.code == "missing_columns"
    assert "account_id" in exc.value.details["missing"]
    assert "net_cash_amount" in exc.value.details["missing"]


def test_read_rows_empty_file_rejected():
    header = ",".join(sorted(_REQUIRED_COLUMNS))
    with pytest.raises(LedgerImportError) as exc:
        _read_rows(header + "\n")
    assert exc.value.code == "empty_file"


# ---- _parse_row ----


def test_parse_row_quantity_is_shares_only_on_trade():
    for row in _parsed("base.csv"):
        if row.activity_type != "Trade":
            assert row.quantity is None
        else:
            assert row.quantity is not None


def test_parse_row_both_same_day_cent_interest_rows_survive():
    interest_rows = [r for r in _parsed("base.csv") if r.activity_type == "Interest"]
    assert len(interest_rows) == 2
    assert all(r.net_cash_amount == pytest.approx(0.01) for r in interest_rows)
    # They differ only in description (one carries FX text, one doesn't) —
    # this is exactly the case the original dedup-key proposal collided on.
    assert interest_rows[0].description != interest_rows[1].description


def test_parse_row_fx_rate_present_on_usd_trade_absent_on_cad_listed():
    trades = [r for r in _parsed("base.csv") if r.activity_type == "Trade"]
    aapl_fx_rates = sorted(r.fx_rate for r in trades if r.symbol == "AAPL")
    xeqt_fx_rates = [r.fx_rate for r in trades if r.symbol == "XEQT.TO"]
    # base.csv has two AAPL buys (1.4500, 1.4600 — see the fixture's own
    # description text) and one CAD-listed XEQT.TO buy with no FX text.
    assert aapl_fx_rates == [pytest.approx(1.45), pytest.approx(1.46)]
    assert xeqt_fx_rates == [None]


def test_parse_row_rejects_non_cad_currency():
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(_row(currency="USD"), line_no=2)
    assert exc.value.code == "unsupported_currency"


def test_parse_row_rejects_blank_effective_date():
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(_row(effective_date=""), line_no=2)
    assert exc.value.code == "missing_effective_date"


def test_parse_row_rejects_blank_effective_time():
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(_row(effective_time=""), line_no=2)
    assert exc.value.code == "missing_effective_date"


def test_parse_row_rejects_malformed_number():
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(_row(net_cash_amount="not-a-number"), line_no=5)
    assert exc.value.code == "malformed_row"
    assert exc.value.details["line"] == 5


def test_parse_row_blank_nullable_fields_become_none():
    row = _parse_row(_row(direction="", symbol="", name=""), line_no=2)
    assert row.direction is None
    assert row.symbol is None
    assert row.name is None


# ---- _check_allowlist ----


def test_check_allowlist_passes_base_csv():
    _check_allowlist(_parsed("base.csv"))  # no raise


def test_check_allowlist_rejects_unknown_type_with_example_and_count():
    with pytest.raises(LedgerImportError) as exc:
        _check_allowlist(_parsed("unknown_type.csv"))
    assert exc.value.code == "unknown_activity_type"
    types = exc.value.details["types"]
    assert len(types) == 1
    assert types[0]["activity_type"] == "Fee"
    assert types[0]["activity_sub_type"] == "MANAGEMENT"
    assert types[0]["count"] == 1


def test_check_allowlist_rejects_sell_on_purpose():
    # Intended behavior (spec, decided pre-2026-09-22): the sell's real
    # strings are unconfirmed, so a sell must trip this until a real one
    # is seen and the allowlist is updated.
    with pytest.raises(LedgerImportError) as exc:
        _check_allowlist(_parsed("with_sell.csv"))
    assert exc.value.code == "unknown_activity_type"
    assert exc.value.details["types"][0]["activity_sub_type"] == "SELL"


# ---- parse_export (end to end) ----


def test_parse_export_base_csv_sorted_and_complete():
    rows = parse_export(_read_bytes("base.csv"))
    assert len(rows) == 9
    assert rows == sorted(rows, key=lambda r: r.effective_at)


def test_parse_export_rejects_missing_effective_date_file():
    with pytest.raises(LedgerImportError) as exc:
        parse_export(_read_bytes("missing_effective_date.csv"))
    assert exc.value.code == "missing_effective_date"


def test_parse_export_rejects_unknown_type_file():
    with pytest.raises(LedgerImportError) as exc:
        parse_export(_read_bytes("unknown_type.csv"))
    assert exc.value.code == "unknown_activity_type"


def test_parse_export_handles_bom():
    content = b"\xef\xbb\xbf" + _read_bytes("base.csv")
    rows = parse_export(content)
    assert len(rows) == 9


def test_parse_export_rejects_non_utf8_bytes():
    with pytest.raises(LedgerImportError) as exc:
        parse_export(b"\xff\xfe\x00 not utf-8 at all")
    assert exc.value.code == "invalid_file"


# ---- a Trade row must carry symbol, quantity and unit_price ----
# compute_positions reads all three on every Trade row; a blank one used to
# reach it and raise AssertionError (a 500) instead of a 422.


@pytest.mark.parametrize("field", ["symbol", "quantity", "unit_price"])
def test_parse_row_rejects_trade_missing_required_field(field):
    raw = _row(activity_type="Trade", activity_sub_type="BUY", symbol="X", quantity="1.0", unit_price="10.0")
    raw[field] = ""
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(raw, line_no=7)
    assert exc.value.code == "malformed_row"
    assert exc.value.details == {"line": 7, "field": field}


@pytest.mark.parametrize("quantity", ["0", "-2"])
def test_parse_row_rejects_non_positive_trade_quantity(quantity):
    raw = _row(activity_type="Trade", activity_sub_type="BUY", symbol="X", quantity=quantity, unit_price="10.0")
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(raw, line_no=3)
    assert exc.value.code == "malformed_row"
    assert exc.value.details["field"] == "quantity"


def test_parse_row_does_not_require_a_symbol_on_non_trade_rows():
    row = _parse_row(_row(activity_type="Interest", activity_sub_type="-", symbol=""), line_no=2)
    assert row.symbol is None


def test_parse_export_rejects_text_the_csv_module_cannot_tokenize():
    # One 200 KB "field" (any large non-CSV text file, e.g. a single-line JSON
    # blob) makes csv raise its own csv.Error, which used to escape as a 500.
    with pytest.raises(LedgerImportError) as exc:
        parse_export(b"x" * 200_000)
    assert exc.value.code == "invalid_file"


# ---- remaining per-row rejections (found untested by a coverage run) ----


@pytest.mark.parametrize(
    ("overrides", "message_part"),
    [
        ({"effective_date": "2026-13-45"}, "effective date/time"),  # not a real date
        ({"effective_time": "9:30"}, "effective date/time"),  # not HH:MM:SS
        ({"settlement_date": "01/09/2026"}, "settlement_date"),  # wrong format
    ],
)
def test_parse_row_rejects_unparseable_dates(overrides, message_part):
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(_row(**overrides), line_no=4)
    assert exc.value.code == "malformed_row"
    assert exc.value.details == {"line": 4}
    assert message_part in exc.value.message


def test_parse_row_rejects_blank_net_cash_amount():
    with pytest.raises(LedgerImportError) as exc:
        _parse_row(_row(net_cash_amount=""), line_no=6)
    assert exc.value.code == "malformed_row"
    assert exc.value.details == {"line": 6}
