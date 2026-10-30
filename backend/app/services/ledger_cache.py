"""In-memory cache of the derived ledger snapshot (issue #19). Positions are
never stored (decision from #33): `activities` is the permanent source of
truth, and this holds a rebuildable copy of what compute_positions made of it.
See .doc/diagrams/ledger-cache-lifecycle-sequence.html."""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.services.portfolio import MergedHolding, merge_holdings
from app.services.positions import compute_positions


@dataclass(frozen=True)
class LedgerSnapshot:
    """What the ledger adds up to right now. An empty ledger is a valid
    snapshot (no holdings, cash 0), not a missing one."""

    holdings: tuple[MergedHolding, ...]
    cash: float
    invested_cad: float  # what the held shares cost in CAD, at the rates of the days they were bought; required so a new caller cannot silently show 0


class LedgerCache:
    """Created once in lifespan (app.state.ledger_cache). The import and reset
    routes call invalidate() after they commit; the next get() rebuilds.

    _snapshot  None means "not loaded", never "empty ledger".
    _lock      one cold read at a time, so a burst of requests after an
               invalidate() runs one query, not many.
    _version   bumped by invalidate(). A load that started before an
               invalidate() may have read pre-commit rows, so it is returned
               to its own caller but not stored.

    Single uvicorn process assumed, like PriceService."""

    def __init__(self) -> None:
        self._snapshot: LedgerSnapshot | None = None
        self._lock = asyncio.Lock()
        self._version = 0

    async def get(self, db: AsyncSession) -> LedgerSnapshot:
        """Cached snapshot, loading it on a miss. Raises LedgerImportError if
        the stored ledger fails the integrity checks; that is not cached, so
        the next call tries again."""
        if self._snapshot is not None:
            return self._snapshot

        async with self._lock:
            if self._snapshot is not None:  # the caller ahead of us filled it
                return self._snapshot

            version = self._version
            snapshot = await self._load(db)
            if version == self._version:  # no import/reset committed meanwhile
                self._snapshot = snapshot
            return snapshot

    def invalidate(self) -> None:
        self._version += 1
        self._snapshot = None

    async def _load(self, db: AsyncSession) -> LedgerSnapshot:
        rows = (await db.execute(select(Activity))).scalars().all()
        holdings, cash, _warnings = compute_positions(rows)  # warnings are an import-time notice (#33)
        invested_cad = sum(h.shares * h.avg_cost_cad for h in holdings)  # per account, before merging: exact
        return LedgerSnapshot(merge_holdings(holdings), cash, invested_cad)
