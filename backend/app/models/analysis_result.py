from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_alert_id: Mapped[int] = mapped_column(
        ForeignKey("stock_alerts.id", ondelete="CASCADE")
    )
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    ticker: Mapped[str] = mapped_column(String)
    triggered_price: Mapped[float] = mapped_column(Float)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")
    action: Mapped[str | None] = mapped_column(String, nullable=True)
    price_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stock_alert: Mapped["StockAlert"] = relationship(  # noqa: F821
        "StockAlert", back_populates="analysis_results"
    )
