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
    # Issue #60 — the used offer's price while the new offer is sold out
    # (AmazonCAScraper's used-only buy box). Information for the UI only,
    # shown while last_scrape_status="oos": never a tracked price, so it has
    # no PriceHistory rows and feeds no chart, comparison or alert. Set on
    # an "oos" scrape (cleared if that scrape has none), cleared on the next
    # "ok", kept through an "error".
    used_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    scraper_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set only alongside last_scrape_status="oos", only when the retailer's
    # own data exposes an expected-back date (e.g. IKEAScraper's per-store
    # restock window, issue #54) — a free-text string, not a real date
    # column, since retailers format this inconsistently ("Sep 22, 2026",
    # a range, etc.) and nothing here needs to query/sort on it. Cleared
    # back to None on the listing's next "ok" scrape, same as any other
    # stale-on-recovery field.
    restock_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # Issue #53 — why the last scrape failed: a short machine-written reason,
    # never a traceback. Set on an "error" result, cleared on the next
    # "ok"/"oos" (a stale reason from three failures ago must not linger once
    # scraping recovers).
    last_scrape_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # When this listing was last polled, whatever the outcome — "ok", "oos"
    # or "error" all count. It's the source of the UI's "last checked"
    # (replacing MAX(PriceHistory.checked_at), which was blind to "oos" since
    # PriceHistory is only written on "ok"). Deliberately not success-only:
    # a failure is already loud (the Failed badge + last_scrape_error), so
    # "last checked" just answers "when did we last try". A listing that
    # stops being polled at all still goes stale. The last *successful*
    # price time stays available in PriceHistory.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
