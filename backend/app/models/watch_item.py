from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Listing(Base):
    """One retailer's URL/price for a `Product`. Table name kept as `watch_items` —
    predates the Product/Listing split (#24) and renaming a live table isn't
    needed for the split to work."""

    __tablename__ = "watch_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True)
    retailer: Mapped[str] = mapped_column(String)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_scrape_status: Mapped[str | None] = mapped_column(String, nullable=True)
    scraper_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    product: Mapped["Product"] = relationship("Product", back_populates="listings")  # noqa: F821
    price_history: Mapped[list["PriceHistory"]] = relationship(  # noqa: F821
        "PriceHistory", back_populates="watch_item", cascade="all, delete-orphan"
    )
