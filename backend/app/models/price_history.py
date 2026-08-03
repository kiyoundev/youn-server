from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_item_id: Mapped[int] = mapped_column(
        ForeignKey("watch_items.id", ondelete="CASCADE")
    )
    price: Mapped[float] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    watch_item: Mapped["Listing"] = relationship(  # noqa: F821
        "Listing", back_populates="price_history"
    )
