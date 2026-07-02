from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StockAlert(Base):
    __tablename__ = "stock_alerts"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "direction", "alert_type", name="uq_stock_alerts_ticker_direction_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String)
    target_price: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String)
    # "buy_signal" (default — price dropped low enough to consider buying),
    # "stop_loss" (sell immediately, direction="below" — distinct urgency, see
    # notify.py), or "take_profit" (sell to lock in gains, direction="above").
    # Lets the same ticker+direction carry multiple alert_types simultaneously
    # at different prices, e.g. buy more at $90, hard-stop sell at $70.
    alert_type: Mapped[str] = mapped_column(String, default="buy_signal", server_default="buy_signal")
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    run_analysis: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Per-alert TradingAgents overrides — null means "inherit the global .env default"
    deep_think_llm: Mapped[str | None] = mapped_column(String, nullable=True)
    quick_think_llm: Mapped[str | None] = mapped_column(String, nullable=True)
    anthropic_effort: Mapped[str | None] = mapped_column(String, nullable=True)
    max_debate_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_risk_discuss_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysts: Mapped[str | None] = mapped_column(String, nullable=True)  # CSV subset

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    analysis_results: Mapped[list["AnalysisResult"]] = relationship(  # noqa: F821
        "AnalysisResult", back_populates="stock_alert", cascade="all, delete-orphan"
    )
