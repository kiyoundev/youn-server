from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api import items
from app.schemas.listing import ListingCreate, ListingUpdate
from app.schemas.product import ProductCreate, ProductUpdate


def _listing(
    listing_id: int = 1,
    *,
    url: str = "https://example.com/p",
    retailer: str = "amazon_ca",
    last_price: float | None = None,
    last_scrape_status: str | None = None,
    active: bool = True,
    product_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=listing_id,
        url=url,
        retailer=retailer,
        last_price=last_price,
        last_scrape_status=last_scrape_status,
        active=active,
        product_id=product_id,
        created_at=datetime.now(timezone.utc),
    )


def _product(
    product_id: int = 1,
    *,
    name: str = "Product",
    target_price: float = 100.0,
    alerted_at: datetime | None = None,
    listings: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=product_id,
        name=name,
        target_price=target_price,
        alerted_at=alerted_at,
        listings=listings if listings is not None else [_listing(product_id=product_id)],
        created_at=datetime.now(timezone.utc),
    )


def _assign_persisted_defaults(obj) -> None:
    """Stand-in for what a real DB flush assigns (id, created_at, column
    defaults, relationship-backpopulated FKs) — the ORM objects the handlers
    construct are real Product/Listing instances, so calling the handler
    directly against a mocked session (no real flush) needs this to satisfy
    the response schemas' non-nullable fields."""
    now = datetime.now(timezone.utc)
    if getattr(obj, "id", None) is None:
        obj.id = 99
    if getattr(obj, "created_at", None) is None:
        obj.created_at = now
    if hasattr(obj, "active") and obj.active is None:
        obj.active = True
    for listing in getattr(obj, "listings", []):
        if getattr(listing, "product_id", None) is None:
            listing.product_id = obj.id
        _assign_persisted_defaults(listing)


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _list_result(values: list):
    scalars = MagicMock()
    scalars.all.return_value = values
    scalars.unique.return_value = scalars
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _rows_result(rows: list[tuple]):
    result = MagicMock()
    result.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_list_items_returns_products_with_computed_fields() -> None:
    listing = _listing(listing_id=1, last_price=90.0, product_id=5)
    product = _product(product_id=5, target_price=100.0, listings=[listing])

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[_list_result([product]), _rows_result([(1, datetime.now(timezone.utc))])]
    )

    result = await items.list_items(db)

    assert len(result) == 1
    assert result[0].id == 5
    assert result[0].status == "watching"
    assert result[0].listings[0].last_price == 90.0
    assert result[0].last_checked is not None


@pytest.mark.asyncio
async def test_get_item_not_found_returns_404() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    with pytest.raises(HTTPException) as exc_info:
        await items.get_item(1, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_item_returns_product() -> None:
    product = _product(product_id=7)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _rows_result([])])

    result = await items.get_item(7, db)

    assert result.id == 7


@pytest.mark.asyncio
async def test_create_item_known_domain_skips_probe() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Watch", target_price=10.0, url="https://www.amazon.ca/dp/B0X")

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect,
    ):
        result = await items.create_item(body, db)

    detect.assert_not_awaited()
    assert result.name == "Watch"
    assert result.listings[0].retailer == "Amazon"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_unknown_domain_probes_and_stores_result() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, url="https://shop.example.com/p")

    with patch(
        "app.api.items.detect_scraper_type", new=AsyncMock(return_value="patchright")
    ) as detect:
        result = await items.create_item(body, db)

    detect.assert_awaited_once_with(body.url)
    assert result.listings[0].url == body.url


@pytest.mark.asyncio
async def test_create_item_probe_failure_returns_400() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    body = ProductCreate(name="Item", target_price=10.0, url="https://shop.example.com/p")

    with patch(
        "app.api.items.detect_scraper_type",
        new=AsyncMock(side_effect=ValueError("URL not scrapable by any method")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await items.create_item(body, db)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_item_precheck_duplicate_url_returns_409() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(1))
    db.add = MagicMock()

    body = ProductCreate(name="Item", target_price=10.0, url="https://www.amazon.ca/dp/B0X")

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        with pytest.raises(HTTPException) as exc_info:
            await items.create_item(body, db)

    assert exc_info.value.status_code == 409
    detect.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_item_race_duplicate_url_returns_409() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, url="https://www.amazon.ca/dp/B0X")

    with pytest.raises(HTTPException) as exc_info:
        await items.create_item(body, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_listing_product_not_found_returns_404() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with pytest.raises(HTTPException) as exc_info:
        await items.create_listing(1, body, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_listing_adds_to_existing_product() -> None:
    product = _product(product_id=5)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _scalar_result(None)])
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with patch.dict("app.api.items.RETAILER_MAP", {"bestbuy.ca": object()}):
        result = await items.create_listing(5, body, db)

    assert result.product_id == 5
    assert result.retailer == "bestbuy_ca"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_listing_duplicate_url_returns_409() -> None:
    product = _product(product_id=5)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _scalar_result(1)])
    db.add = MagicMock()

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with pytest.raises(HTTPException) as exc_info:
        await items.create_listing(5, body, db)

    assert exc_info.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_update_item_not_found_returns_404() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    with pytest.raises(HTTPException) as exc_info:
        await items.update_item(1, ProductUpdate(name="x"), db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_item_applies_only_provided_fields() -> None:
    product = _product(product_id=1, name="Old", target_price=50.0)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _rows_result([])])
    db.commit = AsyncMock()

    await items.update_item(1, ProductUpdate(target_price=75.0), db)

    assert product.name == "Old"
    assert product.target_price == 75.0
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_item_not_found_returns_404() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    with pytest.raises(HTTPException) as exc_info:
        await items.delete_item(1, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_item_deletes_and_commits() -> None:
    product = _product(product_id=1)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(product))
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    await items.delete_item(1, db)

    db.delete.assert_awaited_once_with(product)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_listing_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await items.update_listing(1, 1, ListingUpdate(active=False), db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_listing_mismatched_product_returns_404() -> None:
    listing = _listing(listing_id=1, product_id=2)
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)

    with pytest.raises(HTTPException) as exc_info:
        await items.update_listing(1, 1, ListingUpdate(active=False), db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_listing_pauses() -> None:
    listing = _listing(listing_id=1, product_id=1, active=True)
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=_rows_result([]))

    result = await items.update_listing(1, 1, ListingUpdate(active=False), db)

    assert listing.active is False
    assert result.active is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_listing_removes_sibling_listing_only() -> None:
    listing = _listing(listing_id=1, product_id=1)
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=1)))
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    await items.delete_listing(1, 1, db)

    db.delete.assert_awaited_once_with(listing)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_listing_last_remaining_deletes_product_too() -> None:
    listing = _listing(listing_id=1, product_id=1)
    product = _product(product_id=1)
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)
    sibling_count_result = MagicMock(scalar_one=MagicMock(return_value=0))
    db.execute = AsyncMock(side_effect=[sibling_count_result, _scalar_result(product)])
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    await items.delete_listing(1, 1, db)

    # Product is fetched via the eager-loading helper (not db.get()) so the
    # ORM cascade has listings loaded before delete — see items.py comment.
    db.delete.assert_awaited_once_with(product)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_listing_history_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await items.get_listing_history(1, 1, 30, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_listing_history_returns_rows() -> None:
    listing = _listing(listing_id=1, product_id=1)
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)

    scalars = MagicMock()
    scalars.all.return_value = ["row1", "row2"]
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    result = await items.get_listing_history(1, 1, 30, db)

    assert result == ["row1", "row2"]
