from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class WatchItem(Base):
    __tablename__ = "watch_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    retailer: Mapped[str] = mapped_column(String)
    target_price: Mapped[float] = mapped_column(Float)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scraper_type: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    price_history: Mapped[list["PriceHistory"]] = relationship(  # noqa: F821
        "PriceHistory", back_populates="watch_item", cascade="all, delete-orphan"
    )
