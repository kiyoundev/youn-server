from datetime import datetime
from typing import Literal

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Lives alongside the model, not in services/ or schemas/ — both
# product_status.py's compute_status() (business logic) and
# schemas/product.py's ProductResponse (API contract) need this type, and
# putting it in either one would make the other import "sideways"/"up" out
# of its usual layer. models/ is the lowest layer both already depend on.
ProductStatus = Literal["watching", "triggered", "paused", "failed", "processing"]


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    target_price: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    listings: Mapped[list["Listing"]] = relationship(  # noqa: F821
        "Listing", back_populates="product", cascade="all, delete-orphan"
    )
