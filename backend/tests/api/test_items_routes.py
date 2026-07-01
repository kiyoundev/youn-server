from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api import items
from app.schemas.watch_item import WatchItemCreate, WatchItemUpdate


def _item(
    item_id: int = 1,
    *,
    name: str = "Item",
    url: str = "https://example.com/p",
    target_price: float = 100.0,
    active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id, name=name, url=url, target_price=target_price, active=active
    )


def _db_no_existing_url() -> MagicMock:
    """MagicMock db where the pre-check SELECT for an existing url finds nothing."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    return db


@pytest.mark.asyncio
async def test_create_item_known_domain_skips_probe() -> None:
    db = _db_no_existing_url()

    body = WatchItemCreate(name="Watch", url="https://www.amazon.ca/dp/B0X", target_price=10.0)

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect,
    ):
        result = await items.create_item(body, db)

    detect.assert_not_awaited()
    assert result.retailer == "amazon_ca"
    assert result.scraper_type is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_explicit_scraper_type_skips_probe() -> None:
    db = _db_no_existing_url()

    body = WatchItemCreate(
        name="Item", url="https://shop.example.com/p", target_price=10.0, scraper_type="patchright"
    )

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        result = await items.create_item(body, db)

    detect.assert_not_awaited()
    assert result.scraper_type == "patchright"


@pytest.mark.asyncio
async def test_create_item_unknown_domain_probes_and_stores_result() -> None:
    db = _db_no_existing_url()

    body = WatchItemCreate(name="Item", url="https://shop.example.com/p", target_price=10.0)

    with patch("app.api.items.detect_scraper_type", new=AsyncMock(return_value="patchright")) as detect:
        result = await items.create_item(body, db)

    detect.assert_awaited_once_with(body.url)
    assert result.scraper_type == "patchright"


@pytest.mark.asyncio
async def test_create_item_probe_failure_returns_400() -> None:
    db = _db_no_existing_url()

    body = WatchItemCreate(name="Item", url="https://shop.example.com/p", target_price=10.0)

    with patch(
        "app.api.items.detect_scraper_type",
        new=AsyncMock(side_effect=ValueError("URL not scrapable by any method")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await items.create_item(body, db)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_item_precheck_duplicate_url_returns_409() -> None:
    """Fast path: pre-check finds the duplicate before the (possibly slow) probe ever runs."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=1))
    )

    body = WatchItemCreate(name="Item", url="https://www.amazon.ca/dp/B0X", target_price=10.0)

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        with pytest.raises(HTTPException) as exc_info:
            await items.create_item(body, db)

    assert exc_info.value.status_code == 409
    detect.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_item_race_duplicate_url_returns_409() -> None:
    """Backstop: pre-check passes but a concurrent insert wins the race — IntegrityError -> 409."""
    db = _db_no_existing_url()
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()

    body = WatchItemCreate(name="Item", url="https://www.amazon.ca/dp/B0X", target_price=10.0)

    with pytest.raises(HTTPException) as exc_info:
        await items.create_item(body, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_item_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await items.get_item(1, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_item_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await items.update_item(1, WatchItemUpdate(name="x"), db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_item_applies_only_provided_fields() -> None:
    item = _item(name="Old", target_price=50.0, active=True)
    db = MagicMock()
    db.get = AsyncMock(return_value=item)
    db.commit = AsyncMock()

    await items.update_item(1, WatchItemUpdate(active=False), db)

    assert item.name == "Old"
    assert item.target_price == 50.0
    assert item.active is False


@pytest.mark.asyncio
async def test_delete_item_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await items.delete_item(1, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_item_deletes_and_commits() -> None:
    item = _item()
    db = MagicMock()
    db.get = AsyncMock(return_value=item)
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    await items.delete_item(1, db)

    db.delete.assert_awaited_once_with(item)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_item_history_not_found_returns_404() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await items.get_item_history(1, 30, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_item_history_returns_rows() -> None:
    item = _item()
    db = MagicMock()
    db.get = AsyncMock(return_value=item)

    scalars = MagicMock()
    scalars.all.return_value = ["row1", "row2"]
    exec_result = MagicMock()
    exec_result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=exec_result)

    result = await items.get_item_history(1, 30, db)

    assert result == ["row1", "row2"]
