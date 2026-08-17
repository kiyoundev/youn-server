import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.background_tasks import spawn
from app.core.db import AsyncSessionLocal, get_db
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.watch_item import Listing
from app.schemas.listing import ListingCreate, ListingResponse, ListingUpdate
from app.schemas.price_history import PriceHistoryResponse
from app.schemas.product import (
    ListingFailure,
    ProductCreate,
    ProductCreateResponse,
    ProductResponse,
    ProductUpdate,
)
from app.scheduler.jobs import process_item
from app.services.product_status import compute_last_checked, compute_status
from app.services.scraper.router import (
    RETAILER_DISPLAY_NAMES,
    RETAILER_MAP,
    RetailerRouter,
    detect_scraper_type,
)

_log = logging.getLogger(__name__)

router = APIRouter()

# Bounds how many detect_scraper_type probes (each up to a real HTTPScraper
# request, possibly escalating to a Patchright headless-browser page load)
# run concurrently in one POST /api/items request. Uncapped gather() would
# let a large URL paste spawn that many concurrent browser pages at once —
# fine at this app's realistic 1-3 URLs/add, but worth bounding for a
# pathological large paste, on a Pi 5 also running every other service in
# the stack. Doesn't throttle the realistic case at all.
_PROBE_CONCURRENCY = 3

# Bounds how many #41 add-time first-scrapes (each a full process_item call —
# real page render, up to ~30s) run concurrently. Deliberately separate from
# _PROBE_CONCURRENCY above despite matching value — that one bounds
# detect_scraper_type's lightweight routing probe, this bounds the much
# heavier real scrape; sharing one pool would let a probe burst and a scrape
# burst compete for the same slots and starve each other, despite very
# different per-call costs. See .plan/41-immediate-first-scrape/challenges.md.
_FIRST_SCRAPE_CONCURRENCY = 3
_first_scrape_semaphore = asyncio.Semaphore(_FIRST_SCRAPE_CONCURRENCY)


class _ProbeResult(NamedTuple):
    url: str
    retailer: str | None = None
    scraper_type: str | None = None
    error: str | None = None


def _hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _derive_retailer(hostname: str) -> str:
    return RETAILER_DISPLAY_NAMES.get(hostname, hostname.replace(".", "_"))


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


async def _resolve_one(url: str, semaphore: asyncio.Semaphore) -> _ProbeResult:
    """Bulk-create's per-URL worker for asyncio.gather — never raises. One bad
    URL must not cancel every other in-flight probe in the same batch, so
    every error is caught and returned as data instead of propagating —
    both the expected case (HTTPException, e.g. unscrapable URL) and any
    unexpected one. asyncio.gather() without return_exceptions=True
    propagates the first raised exception and cancels every other pending
    task; catching only HTTPException here would mean one unanticipated bug
    (a real risk in scraper code, which deals with unpredictable external
    HTML/network conditions) 500s the entire request instead of failing
    just its own URL, defeating the point of the concurrent-batch design."""
    async with semaphore:
        try:
            retailer, scraper_type = await _resolve_retailer_and_scraper_type(url, None, None)
            return _ProbeResult(url=url, retailer=retailer, scraper_type=scraper_type)
        except HTTPException as e:
            return _ProbeResult(url=url, error=str(e.detail))
        except Exception:
            _log.exception("Unexpected error probing %s during bulk create", url)
            return _ProbeResult(url=url, error="Unexpected error while probing this URL")


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


async def _bounded_process_item(
    listing_id: int, semaphore: asyncio.Semaphore, queue: asyncio.Queue
) -> None:
    """Runs process_item under the first-scrape concurrency bound, called via
    spawn() so it outlives the request/response cycle that triggered it — see
    .doc/keynotes.md's asyncio concurrency section for why spawn() itself
    needs no reference-holding help here (it already keeps one via
    _background_tasks). A fresh RetailerRouter per call is deliberate, not a
    corner cut — it's stateless (no __init__), so there's nothing to share by
    reusing one across concurrent calls.

    Must never let an exception escape — this runs inside a detached
    asyncio.Task (see spawn()); an unhandled exception here doesn't crash
    anything visibly, it just becomes an "exception was never retrieved"
    warning while the listing is stuck at last_scrape_status=None (reads as
    permanently "Processing" in the UI) until the next scheduled poll_prices
    cycle happens to retry it, up to 6h later, same failure mode
    trading_agents.py's run_analysis already guards against for the same
    reason. process_item's own scraper calls already catch realistic
    failures and return status="error" — this is the backstop for what's
    left (a DB hiccup, an unexpected bug), so it only writes "error" if the
    listing is still unscraped, never stomping a status process_item itself
    already committed (e.g. if the failure were in the trailing broadcast()
    call, after a real successful scrape+commit)."""
    async with semaphore:
        try:
            await process_item(listing_id, RetailerRouter(), queue)
        except Exception:
            _log.error("first-scrape failed for listing %d", listing_id, exc_info=True)
            try:
                async with AsyncSessionLocal() as session:
                    listing = await session.get(Listing, listing_id)
                    if listing is not None and listing.last_scrape_status is None:
                        listing.last_scrape_status = "error"
                        await session.commit()
            except Exception:
                _log.error(
                    "first-scrape: failed to persist error status for listing %d",
                    listing_id,
                    exc_info=True,
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
    response_model=ProductCreateResponse,
    status_code=201,
    summary="Add a new wishlist product",
    description=(
        "Creates a new `Product` and, in the same request, as many of `urls` "
        "as succeed — deriving `retailer` from each URL's hostname and "
        "auto-detecting `scraper_type` via the scraper extraction hierarchy. "
        "Probes run concurrently (bounded), not one at a time. `urls` may be "
        "empty (product created with no listings, for callers that add "
        "listings separately via `POST /api/items/{id}/listings`). A "
        "duplicate URL (within the request or against an existing listing) "
        "or an unscrapable URL is reported in `failed`, not raised as an "
        "error for the whole request — the product and every other "
        "successful listing are still created."
    ),
)
async def create_item(
    request: Request, body: ProductCreate, db: AsyncSession = Depends(get_db)
) -> ProductCreateResponse:
    product = Product(name=body.name, target_price=body.target_price)
    # Materialize the relationship in-memory now, even if it stays empty —
    # otherwise, when every URL fails validation (or urls=[]) and .append()
    # below never runs, the very first access to product.listings happens
    # after commit inside _build_product_response, outside any awaited
    # context. AsyncSessionLocal uses expire_on_commit=False, so an
    # already-loaded collection survives commit fine — but a genuinely
    # never-touched one still triggers SQLAlchemy's first lazy-load on next
    # access, which can't run synchronously and raises MissingGreenlet.
    product.listings = []
    failed: list[ListingFailure] = []

    # In-batch dedup first — two identical URLs pasted into the same request
    # would otherwise both pass the "not already in the DB" check below and
    # race each other for the same listing slot.
    seen: set[str] = set()
    candidates: list[str] = []
    for url in body.urls:
        if url in seen:
            failed.append(ListingFailure(url=url, detail="Duplicate URL within this request"))
            continue
        seen.add(url)
        candidates.append(url)

    existing_urls: set[str] = set()
    if candidates:
        existing = await db.execute(select(Listing.url).where(Listing.url.in_(candidates)))
        existing_urls = {row[0] for row in existing.all()}
        for url in candidates:
            if url in existing_urls:
                failed.append(ListingFailure(url=url, detail="An item with this URL already exists"))

    to_probe = [url for url in candidates if url not in existing_urls]
    if to_probe:
        semaphore = asyncio.Semaphore(_PROBE_CONCURRENCY)
        results = await asyncio.gather(*(_resolve_one(url, semaphore) for url in to_probe))
        for result in results:
            if result.error is not None:
                failed.append(ListingFailure(url=result.url, detail=result.error))
            else:
                product.listings.append(
                    Listing(url=result.url, retailer=result.retailer, scraper_type=result.scraper_type)
                )

    db.add(product)
    try:
        await db.commit()
    except IntegrityError:
        # Rare race: a URL passed the existing-URL check above but another
        # request committed the same URL first, between that check and this
        # commit. IntegrityError doesn't tell us which row collided, so the
        # whole create fails here rather than silently guessing which
        # listing to drop — same 409 shape as every other duplicate case,
        # just covering the window this route's single existing-URL query
        # can't close on its own.
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="One or more URLs were claimed by another request — try again"
        )

    # Fire-and-forget — not awaited, so the response below builds and returns
    # while these scrapes run in the background. Only successfully-created
    # listings are here (product.listings never got the failed ones
    # appended), so nothing extra to filter.
    for listing in product.listings:
        spawn(
            _bounded_process_item(
                listing.id, _first_scrape_semaphore, request.app.state.event_queue
            )
        )

    return ProductCreateResponse(product=_build_product_response(product, {}), failed=failed)


@router.post(
    "/api/items/{product_id}/listings",
    response_model=ListingResponse,
    status_code=201,
    summary="Add a retailer listing to an existing product",
    description="Same retailer-derivation and `scraper_type` auto-detection as `POST /api/items`.",
)
async def create_listing(
    request: Request, product_id: int, body: ListingCreate, db: AsyncSession = Depends(get_db)
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

    # Fire-and-forget, same as create_item above — not awaited.
    spawn(
        _bounded_process_item(listing.id, _first_scrape_semaphore, request.app.state.event_queue)
    )

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
    summary="Update a listing — pause/unpause, and/or change its URL",
    description=(
        "Partial update. `active` toggles pause/resume. `url`, when given and "
        "different from the current value, re-derives `retailer` (unless "
        "overridden via `retailer`) and re-detects `scraper_type` the same way "
        "`POST /api/items/{id}/listings` does — a URL change is treated as a "
        "new page, not just a cosmetic edit. Preserves the listing's `id` and "
        "price history, unlike delete-and-recreate."
    ),
)
async def update_listing(
    product_id: int, listing_id: int, body: ListingUpdate, db: AsyncSession = Depends(get_db)
) -> ListingResponse:
    listing = await _get_listing_or_404(product_id, listing_id, db)

    if body.active is not None:
        listing.active = body.active

    if body.url is not None and body.url != listing.url:
        existing = await db.execute(
            select(Listing.id).where(Listing.url == body.url, Listing.id != listing_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="An item with this URL already exists")

        retailer, scraper_type = await _resolve_retailer_and_scraper_type(
            body.url, body.retailer, None
        )
        listing.url = body.url
        listing.retailer = retailer
        listing.scraper_type = scraper_type

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

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
