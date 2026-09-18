from datetime import datetime

from app.models.product import ProductStatus
from app.models.watch_item import Listing


def compute_status(
    listings: list[Listing],
    product_active: bool,
    alerted_at: datetime | None,
    in_flight_listing_ids: set[int] | None = None,
) -> ProductStatus:
    """Roll up a product's listings + its own active flag into one status.

    Priority, first match wins:
    1. Product inactive -> paused
    2. Any listing never scraped since creation, OR currently mid-scrape
       (issue #45 follow-up — a scheduled/manual re-scrape of an
       already-scraped listing, see services/scrape_tracking.py) ->
       processing
    3. Any listing errored on its last scrape -> failed
    4. Any listing out of stock on its last scrape -> out_of_stock (issue
       #54 — previously fell through to "watching" unconditionally, since
       no branch here ever checked for "oos" at all; a broken scraper
       (failed) still outranks a confirmed-accurate "can't buy it right
       now" reading, so this is checked after failed, not before)
    5. Product has an active alert -> triggered
    6. Otherwise -> watching

    `in_flight_listing_ids` defaults to None/empty and is checked with a
    truthiness guard before ever touching `listing.id` — keeps this
    function's existing callers/tests (many predate `Listing.id` being
    relevant here) working unchanged when no scrape is in flight.
    """
    if not product_active:
        return "paused"

    if any(listing.last_scrape_status is None for listing in listings):
        return "processing"

    if in_flight_listing_ids and any(listing.id in in_flight_listing_ids for listing in listings):
        return "processing"

    if any(listing.last_scrape_status == "error" for listing in listings):
        return "failed"

    if any(listing.last_scrape_status == "oos" for listing in listings):
        return "out_of_stock"

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
