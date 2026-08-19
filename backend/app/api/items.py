import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import httpx
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
from app.scheduler.jobs import _dispatch_first_scrapes, process_item
from app.schemas.listing import ListingCreate, ListingResponse, ListingUpdate
from app.schemas.price_history import PriceHistoryResponse
from app.schemas.product import (
    ListingFailure,
    ProductCreate,
    ProductCreateResponse,
    ProductResponse,
    ProductUpdate,
)
from app.services.product_status import compute_last_checked, compute_status
from app.services.scraper.base import USER_AGENTS, _build_headers
from app.services.scraper.config import HTTP_TIMEOUT_SECONDS
from app.services.scraper.router import (
    RETAILER_MAP,
    _derive_retailer,
    _hostname_of,
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


async def _resolve_final_url(url: str) -> str:
    """Follow redirects to `url`'s actual destination before RETAILER_MAP
    routing decides on it (#39) — a shortlink (a.co, amzn.to, or any other
    retailer's shortener) never matches its destination's entry otherwise,
    since the un-resolved hostname is what gets checked. HEAD first
    (cheaper — the response body is never needed, just the final URL);
    some sites reject/mishandle HEAD, so fall back to GET on a non-2xx
    status. Any network failure (DNS, timeout, connection refused, ...)
    means we can't even find out where this URL goes, so it's raised the
    same way an unscrapable URL is — callers already treat HTTPException
    as a per-URL failure, not a whole-request one."""
    try:
        ua = random.choice(USER_AGENTS)
        async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS, http2=True) as client:
            try:
                resp = await client.head(url, headers=_build_headers(ua))
                if resp.status_code >= 400:
                    resp = await client.get(url, headers=_build_headers(ua))
            except httpx.HTTPError:
                # Some sites don't cleanly 4xx/5xx a HEAD they dislike —
                # they drop the connection, hang, or send a malformed
                # response instead, which httpx surfaces as an exception,
                # not a status code. Retry as GET before giving up, same as
                # the status-code fallback above; only a GET failure means
                # the URL is actually unreachable.
                resp = await client.get(url, headers=_build_headers(ua))
        return str(resp.url)
    except httpx.HTTPError as e:
        # Narrowed to httpx's own exceptions — network/protocol failures
        # only. A bug in this function itself (not a network problem)
        # should surface as a 500, not get reported to the user as "URL
        # could not be resolved".
        _log.warning("URL resolution failed for %s", url, exc_info=True)
        raise HTTPException(status_code=400, detail="URL could not be resolved") from e


async def _resolve_retailer_and_scraper_type(url: str, retailer: str | None, scraper_type: str | None) -> tuple[str, str, str | None]:
    """Shared by both POST endpoints: resolve `url` to its final destination
    first (#39 — following any redirects, e.g. a.co/amzn.to shortlinks), then
    derive `retailer` from the resolved hostname unless explicitly given, and
    auto-detect `scraper_type` via the scraper extraction hierarchy unless
    the resolved hostname is pre-registered or an explicit override was
    provided. Returns the resolved URL too — callers must store/use it
    instead of the original, since RetailerRouter.get_price
    (app/services/scraper/router.py) re-derives hostname from whatever URL
    ends up on the Listing on every scheduled poll; storing the shortlink
    would leave it routing wrong forever, not just failing this one add."""
    resolved_url = await _resolve_final_url(url)
    hostname = _hostname_of(resolved_url)
    resolved_retailer = retailer or _derive_retailer(hostname)

    if hostname in RETAILER_MAP:
        return resolved_url, resolved_retailer, None
    if scraper_type is not None:
        return resolved_url, resolved_retailer, scraper_type
    try:
        detected = await detect_scraper_type(resolved_url)
    except ValueError:
        raise HTTPException(status_code=400, detail="URL could not be scraped by any available method")
    return resolved_url, resolved_retailer, detected


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
            resolved_url, retailer, scraper_type = await _resolve_retailer_and_scraper_type(url, None, None)
            return _ProbeResult(url=resolved_url, retailer=retailer, scraper_type=scraper_type)
        except HTTPException as e:
            return _ProbeResult(url=url, error=str(e.detail))
        except Exception:
            _log.exception("Unexpected error probing %s during bulk create", url)
            return _ProbeResult(url=url, error="Unexpected error while probing this URL")


async def _fetch_last_checked_map(db: AsyncSession, listing_ids: list[int] | None = None) -> dict[int, datetime]:
    query = select(PriceHistory.watch_item_id, func.max(PriceHistory.checked_at))
    if listing_ids is not None:
        query = query.where(PriceHistory.watch_item_id.in_(listing_ids))
    result = await db.execute(query.group_by(PriceHistory.watch_item_id))
    return dict(result.all())


def _build_listing_response(listing: Listing, last_checked_map: dict[int, datetime]) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        retailer=listing.retailer,
        url=listing.url,
        last_price=listing.last_price,
        last_scrape_status=listing.last_scrape_status,
        last_checked=last_checked_map.get(listing.id),
        product_id=listing.product_id,
        created_at=listing.created_at,
    )


def _build_product_response(product: Product, last_checked_map: dict[int, datetime]) -> ProductResponse:
    listing_responses = [_build_listing_response(listing, last_checked_map) for listing in product.listings]
    return ProductResponse(
        id=product.id,
        name=product.name,
        target_price=product.target_price,
        alerted_at=product.alerted_at,
        status=compute_status(product.listings, product.active, product.alerted_at),
        last_checked=compute_last_checked([lr.last_checked for lr in listing_responses]),
        listings=listing_responses,
        created_at=product.created_at,
    )


async def _get_product_or_404(product_id: int, db: AsyncSession) -> Product:
    result = await db.execute(select(Product).options(selectinload(Product.listings)).where(Product.id == product_id))
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
    last_checked_map = await _fetch_last_checked_map(db, [listing.id for listing in product.listings])
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
async def create_item(request: Request, body: ProductCreate, db: AsyncSession = Depends(get_db)) -> ProductCreateResponse:
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
            failed.append(ListingFailure(url=url, detail="Duplicate URL within this request", retailer=_derive_retailer(_hostname_of(url))))
            continue
        seen.add(url)
        candidates.append(url)

    existing_urls: set[str] = set()
    if candidates:
        existing = await db.execute(select(Listing.url).where(Listing.url.in_(candidates)))
        existing_urls = {row[0] for row in existing.all()}
        for url in candidates:
            if url in existing_urls:
                failed.append(ListingFailure(url=url, detail="An item with this URL already exists", retailer=_derive_retailer(_hostname_of(url))))

    to_probe = [url for url in candidates if url not in existing_urls]
    if to_probe:
        semaphore = asyncio.Semaphore(_PROBE_CONCURRENCY)
        results = await asyncio.gather(*(_resolve_one(url, semaphore) for url in to_probe))

        # Resolution (#39) can land two different pasted URLs on the same
        # real destination — two shortlinks, or a shortlink alongside its
        # own already-tracked resolved URL — which the pre-resolve dedup
        # checks above (seen/existing_urls, both against raw candidates)
        # can't catch. Listing.url is DB-unique, so without this second
        # pass, gather()'s succeeded set would 409 the *whole* commit
        # instead of degrading just the colliding URL — same invariant the
        # rest of this function protects (one bad URL can't cancel the
        # others).
        succeeded_resolved = [r.url for r in results if r.error is None]
        resolved_existing: set[str] = set()
        if succeeded_resolved:
            existing_resolved = await db.execute(select(Listing.url).where(Listing.url.in_(succeeded_resolved)))
            resolved_existing = {row[0] for row in existing_resolved.all()}

        seen_resolved: set[str] = set()
        for original_url, result in zip(to_probe, results):
            if result.error is not None:
                # result.retailer is always None here — resolution itself
                # failed, so no successful hostname resolution to derive
                # from; fall back to the original (possibly unresolved) URL.
                failed.append(ListingFailure(url=original_url, detail=result.error, retailer=_derive_retailer(_hostname_of(original_url))))
            elif result.url in resolved_existing or result.url in seen_resolved:
                # result.retailer is already populated here (resolution
                # succeeded) — more accurate than re-deriving from the URL.
                failed.append(ListingFailure(url=original_url, detail="An item with this URL already exists", retailer=result.retailer or _derive_retailer(_hostname_of(original_url))))
            else:
                seen_resolved.add(result.url)
                product.listings.append(Listing(url=result.url, retailer=result.retailer, scraper_type=result.scraper_type))

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
        raise HTTPException(status_code=409, detail="One or more URLs were claimed by another request — try again")

    # Fire-and-forget — not awaited, so the response below builds and returns
    # while these scrapes run in the background. Only successfully-created
    # listings are here (product.listings never got the failed ones
    # appended), so nothing extra to filter. One task for the whole request's
    # batch, not one per listing — see _dispatch_first_scrapes.
    if product.listings:
        spawn(
            _dispatch_first_scrapes(
                [listing.id for listing in product.listings],
                _first_scrape_semaphore,
                request.app.state.event_queue,
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
async def create_listing(request: Request, product_id: int, body: ListingCreate, db: AsyncSession = Depends(get_db)) -> ListingResponse:
    await _get_product_or_404(product_id, db)

    existing = await db.execute(select(Listing.id).where(Listing.url == body.url))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    # No second pre-commit check against the *resolved* URL here, unlike
    # create_item's post-gather pass — this is a single URL, not a batch, so
    # there's no "one bad URL shouldn't cancel the others" invariant to
    # protect. A resolved-URL collision (this shortlink turns out to point
    # at an already-tracked destination) still gets caught, just later: the
    # IntegrityError → 409 handler below fires at commit, same message
    # either way.
    resolved_url, retailer, scraper_type = await _resolve_retailer_and_scraper_type(body.url, body.retailer, body.scraper_type)

    listing = Listing(url=resolved_url, retailer=retailer, scraper_type=scraper_type, product_id=product_id)
    db.add(listing)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An item with this URL already exists")

    # Fire-and-forget, same as create_item above — not awaited. Single-element
    # batch, unifying both call sites on the same _dispatch_first_scrapes
    # mechanism instead of diverging.
    spawn(_dispatch_first_scrapes([listing.id], _first_scrape_semaphore, request.app.state.event_queue))

    return _build_listing_response(listing, {})


@router.patch(
    "/api/items/{product_id}",
    response_model=ProductResponse,
    summary="Update a wishlist product",
    description=(
        "Partial update — omitted fields are left unchanged. `active` "
        "toggles pause/resume for the whole product — while false, none of "
        "its listings are scraped by poll_prices, regardless of their own "
        "state."
    ),
)
async def update_item(product_id: int, body: ProductUpdate, db: AsyncSession = Depends(get_db)) -> ProductResponse:
    product = await _get_product_or_404(product_id, db)

    if body.name is not None:
        product.name = body.name
    if body.target_price is not None:
        product.target_price = body.target_price
    if body.active is not None:
        product.active = body.active

    await db.commit()
    last_checked_map = await _fetch_last_checked_map(db, [listing.id for listing in product.listings])
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
    summary="Update a listing — change its URL",
    description=(
        "Changes a listing's URL (optionally with a `retailer` override) — "
        "the only mutable field left here. When `url` differs from the "
        "current value, `retailer` is re-derived (unless overridden) and "
        "`scraper_type` re-detected the same way `POST "
        "/api/items/{id}/listings` does — a URL change is treated as a new "
        "page, not just a cosmetic edit. Preserves the listing's `id` and "
        "price history, unlike delete-and-recreate. Pause/resume is "
        "product-level only — see `PATCH /api/items/{id}`'s `active` field."
    ),
)
async def update_listing(product_id: int, listing_id: int, body: ListingUpdate, db: AsyncSession = Depends(get_db)) -> ListingResponse:
    listing = await _get_listing_or_404(product_id, listing_id, db)

    if body.url is not None and body.url != listing.url:
        existing = await db.execute(select(Listing.id).where(Listing.url == body.url, Listing.id != listing_id))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="An item with this URL already exists")

        # Same as create_listing above — a resolved-URL collision not caught
        # by this raw-URL pre-check still gets caught at commit's
        # IntegrityError → 409 handler below.
        resolved_url, retailer, scraper_type = await _resolve_retailer_and_scraper_type(body.url, body.retailer, None)
        listing.url = resolved_url
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
        "Cascades to that listing's price history. If it was the product's last remaining listing, the now-empty product is deleted too."
    ),
)
async def delete_listing(product_id: int, listing_id: int, db: AsyncSession = Depends(get_db)) -> None:
    listing = await _get_listing_or_404(product_id, listing_id, db)

    sibling_count = await db.execute(select(func.count(Listing.id)).where(Listing.product_id == product_id, Listing.id != listing_id))
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
