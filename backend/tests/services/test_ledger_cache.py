import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import ledger_cache
from app.services.ledger_cache import LedgerCache
from app.services.ledger_errors import LedgerImportError


def _row(day: int, activity_type: str, **kw) -> SimpleNamespace:
    base = dict(
        account_id="TFSA",
        effective_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        activity_type=activity_type,
        symbol=None,
        quantity=None,
        unit_price=None,
        net_cash_amount=0.0,
        currency="CAD",
        fx_rate=None,
    )
    return SimpleNamespace(**{**base, **kw})


def _deposit(day: int = 1, amount: float = 1000.0) -> SimpleNamespace:
    return _row(day, "MoneyMovement", net_cash_amount=amount)


class _FakeDb:
    """Stands in for AsyncSession: execute() returns the current `rows` and
    counts calls. `gate` holds a query open so tests can interleave."""

    def __init__(self, rows: list) -> None:
        self.rows = rows
        self.queries = 0
        self.gate: asyncio.Event | None = None

    async def execute(self, _stmt):
        self.queries += 1
        rows = list(self.rows)  # what the query "sees" when it starts
        if self.gate is not None:
            await self.gate.wait()
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result


@pytest.fixture
def db() -> _FakeDb:
    return _FakeDb([_deposit()])


async def test_second_get_issues_no_query(db) -> None:
    cache = LedgerCache()

    first = await cache.get(db)
    second = await cache.get(db)

    assert db.queries == 1
    assert second is first
    assert first.cash == 1000.0


async def test_invalidate_forces_a_reload(db) -> None:
    cache = LedgerCache()
    await cache.get(db)

    db.rows = [_deposit(), _deposit(2, 500.0)]
    cache.invalidate()
    snapshot = await cache.get(db)

    assert db.queries == 2
    assert snapshot.cash == 1500.0


async def test_empty_ledger_is_cached_as_an_empty_snapshot() -> None:
    db = _FakeDb([])
    cache = LedgerCache()

    first = await cache.get(db)
    await cache.get(db)

    assert (first.holdings, first.cash) == ((), 0.0)
    assert db.queries == 1  # empty is a real answer, not "not loaded"


async def test_concurrent_cold_reads_run_one_query(db) -> None:
    db.gate = asyncio.Event()
    cache = LedgerCache()

    tasks = [asyncio.create_task(cache.get(db)) for _ in range(3)]
    await asyncio.sleep(0)
    db.gate.set()
    snapshots = await asyncio.gather(*tasks)

    assert db.queries == 1
    assert snapshots[0] is snapshots[1] is snapshots[2]


async def test_integrity_error_propagates_and_is_not_cached(db, monkeypatch) -> None:
    cache = LedgerCache()
    real = ledger_cache.compute_positions
    monkeypatch.setattr(
        ledger_cache, "compute_positions", MagicMock(side_effect=LedgerImportError("negative_cash", "negative cash"))
    )

    with pytest.raises(LedgerImportError):
        await cache.get(db)

    monkeypatch.setattr(ledger_cache, "compute_positions", real)
    snapshot = await cache.get(db)  # retried, not stuck on the error

    assert db.queries == 2
    assert snapshot.cash == 1000.0


async def test_load_that_overlaps_an_invalidate_is_not_stored(db) -> None:
    # reader starts, an import commits and invalidates, then the reader's
    # (pre-commit) query finishes: its answer must not outlive the commit
    db.gate = asyncio.Event()
    cache = LedgerCache()
    reader = asyncio.create_task(cache.get(db))
    await asyncio.sleep(0)

    cache.invalidate()
    db.gate.set()
    stale = await reader
    assert stale.cash == 1000.0  # its own caller still gets what it read

    db.gate = None
    db.rows = [_deposit(), _deposit(2, 500.0)]
    fresh = await cache.get(db)

    assert db.queries == 2  # reloaded, did not reuse the pre-commit result
    assert fresh.cash == 1500.0


async def test_snapshot_holdings_are_merged_across_accounts() -> None:
    def buy(account: str, shares: float, price: float, day: int):
        return _row(
            day,
            "Trade",
            account_id=account,
            symbol="NVDA",
            quantity=shares,
            unit_price=price,
            net_cash_amount=-shares * price,
            currency="USD",
            fx_rate=1.35,
        )

    rows = [
        _deposit(1, 10000.0),
        _row(1, "MoneyMovement", account_id="RRSP", net_cash_amount=10000.0),
        buy("TFSA", 10, 100.0, 2),
        buy("RRSP", 5, 130.0, 3),
    ]
    snapshot = await LedgerCache().get(_FakeDb(rows))

    assert [(h.symbol, h.shares) for h in snapshot.holdings] == [("NVDA", 15)]


async def test_snapshot_invested_cad_is_the_cash_paid_for_what_is_still_held() -> None:
    def trade(day: int, symbol: str, qty: float, price: float, cash: float, fx_rate=None):
        return _row(
            day, "Trade", symbol=symbol, quantity=qty, unit_price=price,
            net_cash_amount=cash, fx_rate=fx_rate,
        )

    rows = [
        _deposit(1, 10000.0),
        trade(2, "NVDA", 2, 280.0, -560.0, fx_rate=1.4),  # a USD stock: 560 CAD paid
        trade(3, "XYZ", 10, 20.0, -200.0),                # CAD-native: 200 CAD paid
        trade(4, "ABC", 10, 10.0, -100.0),
        trade(5, "ABC", 4, 12.0, 48.0),                   # sells 4 of 10 at the average: 60 CAD of cost stays
    ]
    snapshot = await LedgerCache().get(_FakeDb(rows))

    assert snapshot.invested_cad == pytest.approx(560.0 + 200.0 + 60.0)


async def test_an_empty_ledger_has_nothing_invested() -> None:
    assert (await LedgerCache().get(_FakeDb([]))).invested_cad == 0.0


async def test_invested_cad_adds_up_across_accounts() -> None:
    rows = [
        _deposit(1, 10000.0),
        _row(1, "MoneyMovement", account_id="RRSP", net_cash_amount=10000.0),
        _row(2, "Trade", account_id="TFSA", symbol="XYZ", quantity=10, unit_price=20.0, net_cash_amount=-200.0),
        _row(3, "Trade", account_id="RRSP", symbol="XYZ", quantity=5, unit_price=30.0, net_cash_amount=-150.0),
    ]
    snapshot = await LedgerCache().get(_FakeDb(rows))

    assert [(h.symbol, h.shares) for h in snapshot.holdings] == [("XYZ", 15)]  # one merged row
    assert snapshot.invested_cad == pytest.approx(350.0)
