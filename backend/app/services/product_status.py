from datetime import datetime

from app.models.product import ProductStatus
from app.models.watch_item import Listing


def compute_status(listings: list[Listing], product_active: bool, alerted_at: datetime | None) -> ProductStatus:
    """Roll up a product's listings + its own active flag into one status.

    Priority, first match wins:
    1. Product inactive -> paused
    2. Any listing never scraped since creation -> processing
    3. Any listing errored on its last scrape -> failed
    4. Product has an active alert -> triggered
    5. Otherwise -> watching
    """
    if not product_active:
        return "paused"

    if any(listing.last_scrape_status is None for listing in listings):
        return "processing"

    if any(listing.last_scrape_status == "error" for listing in listings):
        return "failed"

    if alerted_at is not None:
        return "triggered"

    return "watching"


def compute_last_checked(listing_last_checked: list[datetime | None]) -> datetime | None:
    """Product-level last-checked is the *stalest* listing's own last-checked
    timestamp, so a silently-broken retailer poll stays visible even if a
    sibling listing is updating fine. `None` entries (never scraped) are
    excluded unless every listing is unscraped."""
    known = [value for value in listing_last_checked if value is not None]
    if not known:
        return None
    return min(known)
