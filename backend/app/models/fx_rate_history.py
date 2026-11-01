from datetime import date

from sqlalchemy import Date, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FxRateHistory(Base):
    """One row per (currency, date) ever resolved for a past USD→CAD lookup
    (issue #74) — additive alongside FxRate, which stays the single
    upserted-in-place row per currency used for the live rate. Populated two
    ways: refresh_fx_rates() (services/fx.py) writes today's date on every
    successful daily fetch, and get_rate_history() backfills whatever dates
    a caller asks for that aren't here yet. No fetched_at — a historical
    rate is either known or it isn't, never "stale" the way the live rate
    can be."""

    __tablename__ = "fx_rate_history"
    __table_args__ = (
        UniqueConstraint("currency", "date", name="uq_fx_rate_history_currency_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String)  # "USD" | "KRW" — generic, only USD has a caller today
    date: Mapped[date] = mapped_column(Date)
    rate_to_cad: Mapped[float] = mapped_column(Float)  # same X→CAD convention as FxRate.rate_to_cad
