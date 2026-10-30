"""Derives holdings and cash balance from an ordered activity ledger.
Positions are never stored — every read recomputes them from Activity rows
(issue #33). Pure — no DB, no FastAPI. Called from two places: the import
route (app/api/activities.py), as the integrity-check gate against the
in-memory merged ledger before a commit; and later, #19's read endpoints,
against real rows already in the DB. Those are two different row classes
(ParsedRow here vs. the future Activity model), so this depends on neither
directly — see ActivityLike below."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.services.ledger_errors import LedgerImportError

_log = logging.getLogger(__name__)


class ActivityLike(Protocol):
    """Structural type — the only fields compute_positions reads. Both
    wealthsimple_csv.ParsedRow and the future SQLAlchemy Activity model
    satisfy this automatically, no inheritance needed."""

    effective_at: datetime
    account_id: str
    activity_type: str
    symbol: str | None
    quantity: float | None
    unit_price: float | None
    fx_rate: float | None
    net_cash_amount: float


@dataclass(frozen=True)
class Holding:
    account_id: str
    symbol: str
    shares: float
    native_currency: Literal["CAD", "USD"]
    avg_cost_native: float
    avg_cost_cad: float
    last_traded_at: datetime  # latest Trade row for this (account, symbol)


@dataclass
class _Accumulator:
    last_traded_at: datetime
    shares: float = 0.0
    total_cost_native: float = 0.0
    total_cost_cad: float = 0.0
    seen_fx: bool = False
    seen_no_fx: bool = False


def compute_positions(activities: Sequence[ActivityLike]) -> tuple[list[Holding], float, list[str]]:
    """Returns (holdings, cash, warnings).

    holdings excludes any (account_id, symbol) fully sold down to 0 shares
    — nothing to report, and it sidesteps a divide-by-zero on avg cost; a
    later re-buy of the same symbol starts its cost basis clean.

    warnings is non-fatal, surfaced in the import response (schema.md) —
    currently only "history doesn't start with a funding deposit". Real
    problems (negative shares/cash, a symbol whose trades disagree on FX
    presence) raise LedgerImportError instead, since those mean earlier
    history is missing or the data can't be trusted, not just unusual."""
    if not activities:
        return [], 0.0, []

    rows = sorted(activities, key=lambda a: a.effective_at)
    warnings: list[str] = []

    first = rows[0]
    if not (first.activity_type == "MoneyMovement" and first.net_cash_amount > 0):
        warnings.append(
            f"Ledger doesn't start with a funding deposit (first row: {first.activity_type} "
            f"on {first.effective_at.date()}) — history may start mid-way."
        )

    cash = 0.0
    accumulators: dict[tuple[str, str], _Accumulator] = {}

    for row in rows:
        cash += row.net_cash_amount
        if cash < 0:
            raise LedgerImportError(
                "negative_cash",
                f"Cash balance goes negative at {row.effective_at.date()} — earlier history is likely missing",
                date=row.effective_at,
            )

        if row.activity_type != "Trade":
            continue

        if row.symbol is None or row.quantity is None or row.unit_price is None:
            missing = [
                name
                for name, value in (("symbol", row.symbol), ("quantity", row.quantity), ("unit_price", row.unit_price))
                if value is None
            ]
            raise LedgerImportError(
                "malformed_row",
                f"Trade row on {row.effective_at.date()} is missing {', '.join(missing)}",
                missing=missing,
                date=row.effective_at,
            )
        key = (row.account_id, row.symbol)
        acc = accumulators.setdefault(key, _Accumulator(row.effective_at))
        acc.last_traded_at = row.effective_at  # rows are sorted, so the last trade seen is the latest
        is_buy = row.net_cash_amount <= 0
        cad_cost = -row.net_cash_amount if is_buy else 0.0

        if row.fx_rate is not None:
            acc.seen_fx = True
            native_cost = (row.unit_price / row.fx_rate) * row.quantity if is_buy else 0.0
        else:
            acc.seen_no_fx = True
            native_cost = cad_cost  # CAD-native: native cost == cash paid, same currency

        if acc.seen_fx and acc.seen_no_fx:
            raise LedgerImportError(
                "mixed_native_currency",
                f"{row.symbol} ({row.account_id}) has trades both with and without an FX "
                "rate — can't tell if it's a USD or CAD-native holding",
                account_id=row.account_id,
                symbol=row.symbol,
            )

        if is_buy:
            acc.shares += row.quantity
            acc.total_cost_native += native_cost
            acc.total_cost_cad += cad_cost
        else:
            # Sell: reduce shares at the running average — the avg cost of
            # what remains is unchanged (spec, decision 1).
            if row.quantity > acc.shares + 1e-9:
                raise LedgerImportError(
                    "negative_holdings",
                    f"{row.symbol} ({row.account_id}) sells more shares than held as of "
                    f"{row.effective_at.date()} — earlier history is likely missing",
                    account_id=row.account_id,
                    symbol=row.symbol,
                    date=row.effective_at,
                )
            if acc.shares > 0:
                avg_native = acc.total_cost_native / acc.shares
                avg_cad = acc.total_cost_cad / acc.shares
                acc.total_cost_native -= avg_native * row.quantity
                acc.total_cost_cad -= avg_cad * row.quantity
            acc.shares -= row.quantity
            if acc.shares <= 1e-9:
                # Fully sold — reset so a later re-buy starts a clean cost basis.
                acc.shares = 0.0
                acc.total_cost_native = 0.0
                acc.total_cost_cad = 0.0

    holdings = [
        Holding(
            account_id=account_id,
            symbol=symbol,
            shares=acc.shares,
            native_currency="USD" if acc.seen_fx else "CAD",
            avg_cost_native=acc.total_cost_native / acc.shares,
            avg_cost_cad=acc.total_cost_cad / acc.shares,
            last_traded_at=acc.last_traded_at,
        )
        for (account_id, symbol), acc in accumulators.items()
        if acc.shares > 0
    ]

    if warnings:
        _log.info("compute_positions: %s", "; ".join(warnings))

    return holdings, cash, warnings
