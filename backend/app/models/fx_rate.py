from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FxRate(Base):
    """Cached FX rate, one row per non-CAD currency this app supports
    (issue #45). `currency` is the primary key — there's exactly one row
    per currency, upserted in place by `refresh_fx_rates`, never a history
    table. CAD needs no row of its own; its rate is always 1.0, handled at
    the read layer (`GET /api/fx-rates`), not stored here."""

    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String, primary_key=True)  # "USD" | "KRW"
    # 1 unit of `currency` expressed in CAD (e.g. USD row: 1.3872 means
    # 1 USD = 1.3872 CAD) — already inverted from frankfurter.app's raw
    # CAD-as-base response at fetch time (services/fx.py), not at read time.
    rate_to_cad: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
