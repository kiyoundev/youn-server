from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api import items
from app.schemas.listing import ListingCreate, ListingUpdate
from app.schemas.product import ProductCreate, ProductUpdate
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


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
    db.execute = AsyncMock(side_effect=[_list_result([product]), _rows_result([(1, datetime.now(timezone.utc))])])

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
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Watch", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect,
    ):
        result = await items.create_item(body, db)

    detect.assert_not_awaited()
    assert result.product.name == "Watch"
    assert result.product.listings[0].retailer == "Amazon"
    assert result.failed == []
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_unknown_domain_probes_and_stores_result() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://shop.example.com/p"])

    with patch("app.api.items.detect_scraper_type", new=AsyncMock(return_value="patchright")) as detect:
        result = await items.create_item(body, db)

    detect.assert_awaited_once_with(body.urls[0])
    assert result.product.listings[0].url == body.urls[0]
    assert result.failed == []


@pytest.mark.asyncio
async def test_create_item_probe_failure_reported_in_failed_not_raised() -> None:
    # Behavior change from the old single-URL design: one bad URL no longer
    # aborts the whole request with a 400 — it's reported per-URL in
    # `failed` so it can't cancel other concurrent probes in the same batch
    # (asyncio.gather), and the product (with whatever else succeeded) is
    # still created.
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://shop.example.com/p"])

    with patch(
        "app.api.items.detect_scraper_type",
        new=AsyncMock(side_effect=ValueError("URL not scrapable by any method")),
    ):
        result = await items.create_item(body, db)

    assert result.product.listings == []
    assert result.failed[0].url == "https://shop.example.com/p"
    assert result.failed[0].detail == "URL could not be scraped by any available method"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_precheck_duplicate_url_reported_in_failed_not_raised() -> None:
    # Same behavior change as above, for the duplicate-URL case: the product
    # is still created (possibly with zero listings if every URL collided).
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([("https://www.amazon.ca/dp/B0X",)]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        result = await items.create_item(body, db)

    detect.assert_not_awaited()
    assert result.product.listings == []
    assert result.failed[0].url == "https://www.amazon.ca/dp/B0X"
    assert result.failed[0].detail == "An item with this URL already exists"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_inbatch_duplicate_url_reported_in_failed() -> None:
    # Two identical URLs pasted into the same request — the second is
    # rejected before ever reaching the DB-existing-URL check.
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(
        name="Item",
        target_price=10.0,
        urls=["https://www.amazon.ca/dp/B0X", "https://www.amazon.ca/dp/B0X"],
    )

    with patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}):
        result = await items.create_item(body, db)

    assert len(result.product.listings) == 1
    assert result.failed[0].url == "https://www.amazon.ca/dp/B0X"
    assert result.failed[0].detail == "Duplicate URL within this request"


@pytest.mark.asyncio
async def test_create_item_race_duplicate_url_returns_409() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}):
        with pytest.raises(HTTPException) as exc_info:
            await items.create_item(body, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_without_urls_creates_product_with_no_listings() -> None:
    db = MagicMock()
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Bare Product", target_price=10.0)

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        result = await items.create_item(body, db)

    detect.assert_not_awaited()
    assert result.product.name == "Bare Product"
    assert result.product.listings == []
    assert result.failed == []
    db.execute.assert_not_called()
    db.commit.assert_awaited_once()


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
async def test_update_listing_url_change_rederives_retailer_and_preserves_id() -> None:
    listing = _listing(listing_id=1, product_id=1, url="https://www.amazon.ca/dp/OLD", retailer="Amazon")
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)
    db.commit = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(None), _rows_result([(1, datetime.now(timezone.utc))])])

    with patch.dict("app.api.items.RETAILER_MAP", {"bestbuy.ca": object()}):
        result = await items.update_listing(1, 1, ListingUpdate(url="https://www.bestbuy.ca/p/NEW"), db)

    assert result.id == 1
    assert result.url == "https://www.bestbuy.ca/p/NEW"
    assert result.retailer == "bestbuy_ca"
    assert result.last_checked is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_listing_url_collision_returns_409() -> None:
    listing = _listing(listing_id=1, product_id=1, url="https://www.amazon.ca/dp/OLD")
    db = MagicMock()
    db.get = AsyncMock(return_value=listing)
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(2))

    with pytest.raises(HTTPException) as exc_info:
        await items.update_listing(1, 1, ListingUpdate(url="https://www.bestbuy.ca/already-watched"), db)

    assert exc_info.value.status_code == 409
    assert listing.url == "https://www.amazon.ca/dp/OLD"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_item_single_url_creates_one_listing() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Watch", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}):
        result = await items.create_item(body, db)

    assert len(result.product.listings) == 1
    assert result.product.listings[0].url == body.urls[0]
    assert result.failed == []
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_multiple_urls_probe_concurrently() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(
        name="Multi",
        target_price=10.0,
        urls=["https://shop-a.example.com/p", "https://shop-b.example.com/p"],
    )

    with patch("app.api.items.detect_scraper_type", new=AsyncMock(return_value=None)) as detect:
        result = await items.create_item(body, db)

    assert detect.await_count == 2
    assert {listing.url for listing in result.product.listings} == set(body.urls)
    assert result.failed == []


@pytest.mark.asyncio
async def test_create_item_unexpected_probe_exception_does_not_cancel_siblings() -> None:
    # Regression for review finding: _resolve_one previously only caught
    # HTTPException — an unexpected exception (RuntimeError here, standing
    # in for a real scraper bug) would propagate through asyncio.gather()
    # uncaught, cancelling every other in-flight probe and 500ing the whole
    # request instead of failing just its own URL.
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(
        name="Multi",
        target_price=10.0,
        urls=["https://shop-bad.example.com/p", "https://shop-good.example.com/p"],
    )

    async def _detect_side_effect(url: str) -> str | None:
        if url == "https://shop-bad.example.com/p":
            raise RuntimeError("unexpected boom")
        return None

    with patch("app.api.items.detect_scraper_type", new=AsyncMock(side_effect=_detect_side_effect)):
        result = await items.create_item(body, db)  # must not raise

    assert result.product.listings[0].url == "https://shop-good.example.com/p"
    assert result.failed[0].url == "https://shop-bad.example.com/p"
    assert result.failed[0].detail == "Unexpected error while probing this URL"
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
