import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.ledger_errors import LedgerImportError

# The timezone effective_at is interpreted in (Wealthsimple exports carry naive
# local times). Also the timezone every user-facing date in an import response
# is shown in — see ledger_import.ledger_date.
LEDGER_TZ = ZoneInfo("America/Toronto")

_REQUIRED_COLUMNS = {
    "effective_date",
    "effective_time",
    "settlement_date",
    "account_id",
    "account_type",
    "activity_type",
    "activity_sub_type",
    "description",
    "direction",
    "symbol",
    "name",
    "currency",
    "quantity",
    "unit_price",
    "commission",
    "net_cash_amount",
}

_ACTIVITY_ALLOWLIST = {
    ("Trade", "BUY"),
    ("MoneyMovement", "EFT"),
    ("MoneyMovement", "E_TRFIN"),
    ("Interest", "-"),
    ("Dividend", "-"),
    ("Tax", "NRT"),
}

_FX_RATE_RE = re.compile(r"FX Rate:\s*([\d.]+)")


@dataclass(frozen=True)
class ParsedRow:
    effective_at: datetime
    settlement_date: date | None
    account_id: str
    account_type: str
    activity_type: str
    activity_sub_type: str
    description: str
    direction: str | None
    symbol: str | None
    name: str | None
    currency: str
    quantity: float | None  # shares — Trade rows only, else None
    unit_price: float | None
    fx_rate: float | None
    commission: float
    net_cash_amount: float


def _read_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    try:
        fieldnames = reader.fieldnames
        missing = _REQUIRED_COLUMNS - set(fieldnames or [])
        if missing:
            raise LedgerImportError("missing_columns", "CSV is missing required columns", missing=sorted(missing))
        rows = list(reader)
    except csv.Error as e:
        # The csv module raises its own error for input it can't tokenize —
        # e.g. a single field over 128 KB, which is what a large non-CSV text
        # file looks like. Without this that's a bare 500.
        raise LedgerImportError("invalid_file", f"Couldn't read this as a CSV: {e}") from e
    if not rows:
        raise LedgerImportError("empty_file", "CSV has no data rows")
    return rows


def _opt(raw: dict[str, str], key: str) -> str | None:
    """Blank cell → None, for the nullable string fields."""
    value = raw[key].strip()
    return value or None


def _float(raw: dict[str, str], key: str, line_no: int) -> float | None:
    """Blank cell → None; a present-but-unparseable value fails loudly with
    the line and field so the error is fixable, not a bare ValueError deep
    in the middle of the file."""
    value = raw[key].strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError as e:
        raise LedgerImportError("malformed_row", f"line {line_no}: bad number in {key!r}: {value!r}", line=line_no, field=key) from e


def _parse_row(raw: dict[str, str], line_no: int) -> ParsedRow:
    currency = raw["currency"].strip()
    if currency != "CAD":
        raise LedgerImportError(
            "unsupported_currency",
            f"line {line_no}: currency must be CAD, got {currency!r}",
            line=line_no,
            currency=currency,
        )

    eff_date = raw["effective_date"].strip()
    eff_time = raw["effective_time"].strip()
    if not eff_date or not eff_time:
        raise LedgerImportError("missing_effective_date", f"line {line_no}: effective_date/effective_time is blank", line=line_no)
    try:
        effective_at = datetime.strptime(f"{eff_date} {eff_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=LEDGER_TZ)
    except ValueError as e:
        raise LedgerImportError("malformed_row", f"line {line_no}: bad effective date/time", line=line_no) from e

    settlement_raw = _opt(raw, "settlement_date")
    try:
        settlement_date = datetime.strptime(settlement_raw, "%Y-%m-%d").date() if settlement_raw else None
    except ValueError as e:
        raise LedgerImportError("malformed_row", f"line {line_no}: bad settlement_date", line=line_no) from e

    activity_type = raw["activity_type"].strip()

    # quantity is overloaded in the raw CSV — cash amount on every type
    # except Trade, where it's shares. Only Trade rows get a real value here.
    quantity = _float(raw, "quantity", line_no) if activity_type == "Trade" else None
    unit_price = _float(raw, "unit_price", line_no)
    symbol = _opt(raw, "symbol")
    if activity_type == "Trade":
        # compute_positions reads all three unconditionally on a Trade row —
        # a blank one must be a 422 here, not an AssertionError (a 500) there.
        for field, value in (("symbol", symbol), ("quantity", quantity), ("unit_price", unit_price)):
            if value is None:
                raise LedgerImportError(
                    "malformed_row", f"line {line_no}: Trade row is missing {field}", line=line_no, field=field
                )
        if quantity <= 0:
            raise LedgerImportError(
                "malformed_row",
                f"line {line_no}: Trade quantity must be positive, got {quantity}",
                line=line_no,
                field="quantity",
            )
    commission = _float(raw, "commission", line_no) or 0.0

    net_cash_amount = _float(raw, "net_cash_amount", line_no)
    if net_cash_amount is None:
        raise LedgerImportError("malformed_row", f"line {line_no}: net_cash_amount is required", line=line_no)

    # FX Rate text appears on any row type (US trades, USD-sourced interest),
    # not just Trade — parsed uniformly here regardless of activity_type.
    fx_match = _FX_RATE_RE.search(raw["description"])
    fx_rate = float(fx_match.group(1)) if fx_match else None

    return ParsedRow(
        effective_at=effective_at,
        settlement_date=settlement_date,
        account_id=raw["account_id"].strip(),
        account_type=raw["account_type"].strip(),
        activity_type=activity_type,
        activity_sub_type=raw["activity_sub_type"].strip(),
        description=raw["description"],
        direction=_opt(raw, "direction"),
        symbol=symbol,
        name=_opt(raw, "name"),
        currency=currency,
        quantity=quantity,
        unit_price=unit_price,
        fx_rate=fx_rate,
        commission=commission,
        net_cash_amount=net_cash_amount,
    )


def _check_allowlist(rows: list[ParsedRow]) -> None:
    """Reject the whole file if any row's (activity_type, activity_sub_type)
    isn't a confirmed pair. Runs as a second pass over every already-parsed
    row, after _parse_row — a malformed number or bad date fails first
    (decided 2026-09-22), this check only ever sees well-formed rows.

    Groups every unknown pair together and raises once, with a count and
    one example description per group — so the error is copy-pasteable and
    a file with several unknown rows doesn't need multiple re-uploads to
    discover them all (spec: reject-whole, not skip, so the frozen-past
    rule can't strand a skipped row)."""
    unknown: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.activity_type, row.activity_sub_type)
        if key in _ACTIVITY_ALLOWLIST:
            continue
        group = unknown.setdefault(
            key, {"direction": row.direction, "count": 0, "example": row.description}
        )
        group["count"] += 1

    if not unknown:
        return

    types = [
        {"activity_type": activity_type, "activity_sub_type": activity_sub_type, **group}
        for (activity_type, activity_sub_type), group in unknown.items()
    ]
    raise LedgerImportError(
        "unknown_activity_type",
        f"CSV contains {len(types)} unrecognized activity type(s)",
        types=types,
    )


def parse_export(content: bytes) -> list[ParsedRow]:
    """Public entry point — the only function this module exposes. Turns
    raw uploaded file bytes into a clean, chronologically-sorted list of
    validated rows, or raises LedgerImportError. Nothing below this knows
    about FastAPI/HTTP; the route (app/api/activities.py) is the one place
    that catches LedgerImportError and maps it to an HTTPException."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise LedgerImportError("invalid_file", "File isn't valid UTF-8 text — is it really a CSV export?") from e
    raw_rows = _read_rows(text)
    rows = [_parse_row(r, i + 2) for i, r in enumerate(raw_rows)]
    _check_allowlist(rows)
    return sorted(rows, key=lambda r: r.effective_at)
