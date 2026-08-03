from datetime import datetime
from typing import Literal

from app.models.watch_item import Listing

ProductStatus = Literal["watching", "triggered", "paused", "failed"]


def compute_status(listings: list[Listing], alerted_at: datetime | None) -> ProductStatus:
    """Roll up a product's listings into one status.

    Priority, first match wins:
    1. All listings inactive -> paused (nothing being watched)
    2. Any active listing errored on its last scrape -> failed
    3. Product has an active alert -> triggered
    4. Otherwise -> watching
    """
    active_listings = [listing for listing in listings if listing.active]

    if not active_listings:
        return "paused"

    if any(listing.last_scrape_status == "error" for listing in active_listings):
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
