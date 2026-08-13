from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        # at most one pending/running analysis per ticker at a time — makes the
        # POST /api/stockalerts/{id}/analyze 409 guard race-safe, not just an
        # app-level check-then-insert
        Index(
            "uq_analysis_results_ticker_running",
            "ticker",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_alert_id: Mapped[int] = mapped_column(
        ForeignKey("stock_alerts.id", ondelete="CASCADE")
    )
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    ticker: Mapped[str] = mapped_column(String)
    triggered_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", server_default="pending")
    action: Mapped[str | None] = mapped_column(String, nullable=True)
    price_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stock_alert: Mapped["StockAlert"] = relationship(  # noqa: F821
        "StockAlert", back_populates="analysis_results"
    )
