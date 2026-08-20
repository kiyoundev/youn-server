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
    # Nullable (issue #44) — optional at creation, filled in from the first
    # successful scrape's inferred product_title if the user left it blank.
    # NULL, not a placeholder string, distinguishes "not yet named" from any
    # real (even coincidentally short) user-provided name.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    target_price: Mapped[float] = mapped_column(Float)
    # Nullable (issue #45) — same fill-only-if-null pattern as `name`: set
    # from the first successful scrape's inferred currency, unless the user
    # has already set it manually via PATCH (manual override always wins).
    # ISO 4217 code, app-constrained to Literal["USD","CAD","KRW"] at the
    # Pydantic layer only, no DB CHECK constraint.
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    listings: Mapped[list["Listing"]] = relationship(  # noqa: F821
        "Listing", back_populates="product", cascade="all, delete-orphan"
    )
