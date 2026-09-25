from datetime import date, datetime

from sqlalchemy import DateTime, Date, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Activity(Base):
    """One row per Wealthsimple activity-export line (issue #33) — the
    durable ledger of record. There is no manually maintained Position
    table: holdings, average cost and cash are all derived on read by
    services/positions.py's compute_positions, never stored here.

    No unique constraint — the CSV carries no row id, and two legitimate
    rows can be identical apart from description (same-day $0.01 interest
    postings). Import/dedup correctness rests entirely on date ranges
    (services/ledger_import.py), not row identity."""

    __tablename__ = "activities"
    __table_args__ = (
        # ordering + coverage (earliest/newest stored effective_at per
        # account) — every query this issue makes is keyed by account_id.
        Index("ix_activities_account_effective_at", "account_id", "effective_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_id: Mapped[str] = mapped_column(String)
    account_type: Mapped[str] = mapped_column(String)
    activity_type: Mapped[str] = mapped_column(String)
    activity_sub_type: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)  # shares — Trade rows only
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fx_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    net_cash_amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
