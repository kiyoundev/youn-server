from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.price_history import PriceHistory
from app.models.watch_item import WatchItem
from app.schemas.price_history import PriceHistoryResponse
from app.schemas.watch_item import WatchItemCreate, WatchItemResponse, WatchItemUpdate
from app.services.scraper.router import RETAILER_MAP, detect_scraper_type

router = APIRouter()


def _hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _derive_retailer(hostname: str) -> str:
    return hostname.replace(".", "_")


@router.get(
    "/api/items",
    response_model=list[WatchItemResponse],
    summary="List all wishlist items",
    description="Returns every `WatchItem` row, active and paused alike.",
)
async def list_items(db: AsyncSession = Depends(get_db)) -> list[WatchItem]:
    """List all tracked wishlist items.

    Returns:
        Every `WatchItem` row in the database, regardless of `active` status.
    """
    result = await db.execute(select(WatchItem))
    return list(result.scalars().all())


@router.get(
    "/api/items/{item_id}",
    response_model=WatchItemResponse,
    summary="Get a single wishlist item",
)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)) -> WatchItem:
    """Fetch one wishlist item by ID.

    Args:
        item_id: Primary key of the `WatchItem` row.

    Returns:
        The matching `WatchItem`.

    Raises:
        HTTPException: 404 if no item exists with that ID.
    """
    item = await db.get(WatchItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post(
    "/api/items",
    response_model=WatchItemResponse,
    status_code=201,
    summary="Add a new wishlist item",
    description=(
        "Derives `retailer` from the URL's hostname and probes the URL through "
        "the scraper extraction hierarchy to auto-detect `scraper_type`, unless "
        "an explicit `scraper_type` is provided in the body."
    ),
)
async def create_item(body: WatchItemCreate, db: AsyncSession = Depends(get_db)) -> WatchItem:
    """Create a new wishlist item, auto-detecting its scraper type.

    Args:
        body: New item fields — `name`, `url`, `target_price`, optional
            `scraper_type` override.

    Returns:
        The newly created `WatchItem`.

    Raises:
        HTTPException: 409 if an item with the same URL already exists.
        HTTPException: 400 if the URL couldn't be scraped by any known method
            (only when `scraper_type` isn't explicitly provided and the host
            isn't a pre-registered retailer).
    """
    existing = await db.execute(select(WatchItem.id).where(WatchItem.url == body.url))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    hostname = _hostname_of(body.url)
    retailer = _derive_retailer(hostname)

    if hostname in RETAILER_MAP:
        scraper_type = None
    elif body.scraper_type is not None:
        scraper_type = body.scraper_type
    else:
        try:
            scraper_type = await detect_scraper_type(body.url)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="URL could not be scraped by any available method"
            )

    item = WatchItem(
        name=body.name,
        url=body.url,
        retailer=retailer,
        target_price=body.target_price,
        scraper_type=scraper_type,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An item with this URL already exists")
    return item


@router.patch(
    "/api/items/{item_id}",
    response_model=WatchItemResponse,
    summary="Update a wishlist item",
    description="Partial update — omitted fields are left unchanged.",
)
async def update_item(
    item_id: int, body: WatchItemUpdate, db: AsyncSession = Depends(get_db)
) -> WatchItem:
    """Update name, target price, and/or active status for a wishlist item.

    Args:
        item_id: Primary key of the `WatchItem` row.
        body: Fields to change; any field left as `None` is left untouched.

    Returns:
        The updated `WatchItem`.

    Raises:
        HTTPException: 404 if no item exists with that ID.
    """
    item = await db.get(WatchItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.name is not None:
        item.name = body.name
    if body.target_price is not None:
        item.target_price = body.target_price
    if body.active is not None:
        item.active = body.active

    await db.commit()
    return item


@router.delete(
    "/api/items/{item_id}",
    status_code=204,
    summary="Delete a wishlist item",
    description="Cascades to delete all associated `PriceHistory` rows.",
)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a wishlist item and its price history.

    Args:
        item_id: Primary key of the `WatchItem` row.

    Raises:
        HTTPException: 404 if no item exists with that ID.
    """
    item = await db.get(WatchItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()


@router.get(
    "/api/items/{item_id}/history",
    response_model=list[PriceHistoryResponse],
    summary="Get price history for a wishlist item",
)
async def get_item_history(
    item_id: int, days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)
) -> list[PriceHistory]:
    """Fetch recorded price points for a wishlist item within a lookback window.

    Args:
        item_id: Primary key of the `WatchItem` row.
        days: Lookback window in days (1-365, default 30).

    Returns:
        `PriceHistory` rows within the window, oldest first.

    Raises:
        HTTPException: 404 if no item exists with that ID.
    """
    item = await db.get(WatchItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.watch_item_id == item_id, PriceHistory.checked_at >= cutoff)
        .order_by(PriceHistory.checked_at)
    )
    return list(result.scalars().all())
