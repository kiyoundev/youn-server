from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.watch_item import Listing
from app.schemas.listing import ListingCreate, ListingResponse, ListingUpdate
from app.schemas.price_history import PriceHistoryResponse
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.product_status import compute_last_checked, compute_status
from app.services.scraper.router import RETAILER_MAP, detect_scraper_type

router = APIRouter()


def _hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _derive_retailer(hostname: str) -> str:
    return hostname.replace(".", "_")


async def _resolve_retailer_and_scraper_type(
    url: str, retailer: str | None, scraper_type: str | None
) -> tuple[str, str | None]:
    """Shared by both POST endpoints: derive `retailer` from the URL's hostname
    unless explicitly given, and auto-detect `scraper_type` via the scraper
    extraction hierarchy unless the hostname is pre-registered or an explicit
    override was provided."""
    hostname = _hostname_of(url)
    resolved_retailer = retailer or _derive_retailer(hostname)

    if hostname in RETAILER_MAP:
        return resolved_retailer, None
    if scraper_type is not None:
        return resolved_retailer, scraper_type
    try:
        detected = await detect_scraper_type(url)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="URL could not be scraped by any available method"
        )
    return resolved_retailer, detected


async def _fetch_last_checked_map(
    db: AsyncSession, listing_ids: list[int] | None = None
) -> dict[int, datetime]:
    query = select(PriceHistory.watch_item_id, func.max(PriceHistory.checked_at))
    if listing_ids is not None:
        query = query.where(PriceHistory.watch_item_id.in_(listing_ids))
    result = await db.execute(query.group_by(PriceHistory.watch_item_id))
    return dict(result.all())


def _build_listing_response(
    listing: Listing, last_checked_map: dict[int, datetime]
) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        retailer=listing.retailer,
        url=listing.url,
        last_price=listing.last_price,
        last_scrape_status=listing.last_scrape_status,
        active=listing.active,
        last_checked=last_checked_map.get(listing.id),
        product_id=listing.product_id,
        created_at=listing.created_at,
    )


def _build_product_response(
    product: Product, last_checked_map: dict[int, datetime]
) -> ProductResponse:
    listing_responses = [
        _build_listing_response(listing, last_checked_map) for listing in product.listings
    ]
    return ProductResponse(
        id=product.id,
        name=product.name,
        target_price=product.target_price,
        alerted_at=product.alerted_at,
        status=compute_status(product.listings, product.alerted_at),
        last_checked=compute_last_checked([lr.last_checked for lr in listing_responses]),
        listings=listing_responses,
        created_at=product.created_at,
    )


async def _get_product_or_404(product_id: int, db: AsyncSession) -> Product:
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.listings))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def _get_listing_or_404(product_id: int, listing_id: int, db: AsyncSession) -> Listing:
    listing = await db.get(Listing, listing_id)
    if listing is None or listing.product_id != product_id:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.get(
    "/api/items",
    response_model=list[ProductResponse],
    summary="List all wishlist products",
    description="Returns every `Product`, each with its nested retailer `listings`.",
)
async def list_items(db: AsyncSession = Depends(get_db)) -> list[ProductResponse]:
    result = await db.execute(select(Product).options(selectinload(Product.listings)))
    products = list(result.scalars().unique().all())
    last_checked_map = await _fetch_last_checked_map(db)
    return [_build_product_response(product, last_checked_map) for product in products]


@router.get(
    "/api/items/{product_id}",
    response_model=ProductResponse,
    summary="Get a single wishlist product",
)
async def get_item(product_id: int, db: AsyncSession = Depends(get_db)) -> ProductResponse:
    product = await _get_product_or_404(product_id, db)
    last_checked_map = await _fetch_last_checked_map(
        db, [listing.id for listing in product.listings]
    )
    return _build_product_response(product, last_checked_map)


@router.post(
    "/api/items",
    response_model=ProductResponse,
    status_code=201,
    summary="Add a new wishlist product",
    description=(
        "Creates a new `Product` with its required first `Listing`. Derives "
        "`retailer` from the URL's hostname and probes the URL through the "
        "scraper extraction hierarchy to auto-detect `scraper_type`, unless "
        "an explicit `scraper_type` is provided in the body."
    ),
)
async def create_item(body: ProductCreate, db: AsyncSession = Depends(get_db)) -> ProductResponse:
    existing = await db.execute(select(Listing.id).where(Listing.url == body.url))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    retailer, scraper_type = await _resolve_retailer_and_scraper_type(
        body.url, body.retailer, body.scraper_type
    )

    product = Product(name=body.name, target_price=body.target_price)
    product.listings = [Listing(url=body.url, retailer=retailer, scraper_type=scraper_type)]
    db.add(product)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    return _build_product_response(product, {})


@router.post(
    "/api/items/{product_id}/listings",
    response_model=ListingResponse,
    status_code=201,
    summary="Add a retailer listing to an existing product",
    description="Same retailer-derivation and `scraper_type` auto-detection as `POST /api/items`.",
)
async def create_listing(
    product_id: int, body: ListingCreate, db: AsyncSession = Depends(get_db)
) -> ListingResponse:
    await _get_product_or_404(product_id, db)

    existing = await db.execute(select(Listing.id).where(Listing.url == body.url))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    retailer, scraper_type = await _resolve_retailer_and_scraper_type(
        body.url, body.retailer, body.scraper_type
    )

    listing = Listing(
        url=body.url, retailer=retailer, scraper_type=scraper_type, product_id=product_id
    )
    db.add(listing)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    return _build_listing_response(listing, {})


@router.patch(
    "/api/items/{product_id}",
    response_model=ProductResponse,
    summary="Update a wishlist product",
    description="Partial update — omitted fields are left unchanged. Applies to all listings.",
)
async def update_item(
    product_id: int, body: ProductUpdate, db: AsyncSession = Depends(get_db)
) -> ProductResponse:
    product = await _get_product_or_404(product_id, db)

    if body.name is not None:
        product.name = body.name
    if body.target_price is not None:
        product.target_price = body.target_price

    await db.commit()
    last_checked_map = await _fetch_last_checked_map(
        db, [listing.id for listing in product.listings]
    )
    return _build_product_response(product, last_checked_map)


@router.delete(
    "/api/items/{product_id}",
    status_code=204,
    summary="Delete a wishlist product",
    description="Cascades to delete all listings and their price history.",
)
async def delete_item(product_id: int, db: AsyncSession = Depends(get_db)) -> None:
    product = await _get_product_or_404(product_id, db)
    await db.delete(product)
    await db.commit()


@router.patch(
    "/api/items/{product_id}/listings/{listing_id}",
    response_model=ListingResponse,
    summary="Pause or unpause a listing",
)
async def update_listing(
    product_id: int, listing_id: int, body: ListingUpdate, db: AsyncSession = Depends(get_db)
) -> ListingResponse:
    listing = await _get_listing_or_404(product_id, listing_id, db)

    if body.active is not None:
        listing.active = body.active

    await db.commit()
    last_checked_map = await _fetch_last_checked_map(db, [listing.id])
    return _build_listing_response(listing, last_checked_map)


@router.delete(
    "/api/items/{product_id}/listings/{listing_id}",
    status_code=204,
    summary="Delete a listing",
    description=(
        "Cascades to that listing's price history. If it was the product's last "
        "remaining listing, the now-empty product is deleted too."
    ),
)
async def delete_listing(product_id: int, listing_id: int, db: AsyncSession = Depends(get_db)) -> None:
    listing = await _get_listing_or_404(product_id, listing_id, db)

    sibling_count = await db.execute(
        select(func.count(Listing.id)).where(
            Listing.product_id == product_id, Listing.id != listing_id
        )
    )
    is_last_listing = sibling_count.scalar_one() == 0

    if is_last_listing:
        # Eager-load listings (not db.get()) so the ORM cascade has what it
        # needs without relying on implicit lazy-loading during delete().
        product = await _get_product_or_404(product_id, db)
        await db.delete(product)
    else:
        await db.delete(listing)
    await db.commit()


@router.get(
    "/api/items/{product_id}/listings/{listing_id}/history",
    response_model=list[PriceHistoryResponse],
    summary="Get price history for a listing",
)
async def get_listing_history(
    product_id: int,
    listing_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> list[PriceHistory]:
    await _get_listing_or_404(product_id, listing_id, db)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.watch_item_id == listing_id, PriceHistory.checked_at >= cutoff)
        .order_by(PriceHistory.checked_at)
    )
    return list(result.scalars().all())
