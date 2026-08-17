import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.api import items
from app.schemas.listing import ListingCreate, ListingUpdate
from app.schemas.product import ProductCreate, ProductUpdate
from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import IntegrityError


@pytest.fixture(autouse=True)
def _stub_resolve_final_url():
    """_resolve_retailer_and_scraper_type (#39) now resolves the URL's final
    destination via a real network round-trip before routing — irrelevant to
    most of this file's route-behavior tests, and would otherwise hit a real
    network for a test URL that doesn't exist. Stubbed to an identity no-op
    (returns the URL unchanged, as if it never redirected) so every test
    keeps today's pre-#39 behavior for free; the redirect-specific tests
    below override it locally."""
    with patch("app.api.items._resolve_final_url", new=AsyncMock(side_effect=lambda url: url)) as mock:
        yield mock


@pytest.fixture(autouse=True)
def _stub_first_scrape_dispatch():
    """create_item/create_listing now spawn() a background first-scrape per
    listing (#41) — not what most of this file's route-behavior tests are
    about, and a real _bounded_process_item would open its own
    AsyncSessionLocal() and hit a real network, unrelated to this file's
    mocked `db`. Stubbed so every test in this file gets an inert spawn()
    target for free; yields the mock so the two dispatch-specific tests
    below can assert on it directly."""
    with patch("app.api.items._bounded_process_item", new=AsyncMock()) as mock:
        yield mock


def _request() -> SimpleNamespace:
    """Minimal stand-in for FastAPI's Request — only .app.state.event_queue
    is ever read by create_item/create_listing, same pattern as
    test_poll_routes.py's `request = SimpleNamespace(app=app)`."""
    app = FastAPI()
    app.state.event_queue = asyncio.Queue()
    return SimpleNamespace(app=app)


# Captured at import time, before the autouse fixture above ever patches
# app.api.items._bounded_process_item — this stays bound to the real
# implementation regardless, so the tests below can exercise its own
# exception-guard behavior directly instead of the stub.
_real_bounded_process_item = items._bounded_process_item

# Same pattern, for _resolve_final_url (#39) — the autouse
# _stub_resolve_final_url fixture below patches this name for every other
# test in this file, so _resolve_final_url's own unit tests need the
# unpatched function to actually exercise it.
_real_resolve_final_url = items._resolve_final_url


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeHTTPClient:
    """Stand-in for `httpx.AsyncClient` used only by `_resolve_final_url`'s
    unit tests below — a real client's `async with ... as client:` needs
    `.head`/`.get` to be independently awaitable mocks, not a single
    `_AsyncCM`-wrapped value."""

    def __init__(self, *, head: AsyncMock | None = None, get: AsyncMock | None = None):
        self.head = head or AsyncMock()
        self.get = get or AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
    listing = _listing(listing_id=1, last_price=90.0, last_scrape_status="ok", product_id=5)
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
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Watch", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect,
    ):
        result = await items.create_item(request, body, db)

    detect.assert_not_awaited()
    assert result.product.name == "Watch"
    assert result.product.listings[0].retailer == "Amazon"
    assert result.failed == []
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_unknown_domain_probes_and_stores_result() -> None:
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://shop.example.com/p"])

    with patch("app.api.items.detect_scraper_type", new=AsyncMock(return_value="patchright")) as detect:
        result = await items.create_item(request, body, db)

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
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://shop.example.com/p"])

    with patch(
        "app.api.items.detect_scraper_type",
        new=AsyncMock(side_effect=ValueError("URL not scrapable by any method")),
    ):
        result = await items.create_item(request, body, db)

    assert result.product.listings == []
    assert result.failed[0].url == "https://shop.example.com/p"
    assert result.failed[0].detail == "URL could not be scraped by any available method"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_precheck_duplicate_url_reported_in_failed_not_raised() -> None:
    # Same behavior change as above, for the duplicate-URL case: the product
    # is still created (possibly with zero listings if every URL collided).
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([("https://www.amazon.ca/dp/B0X",)]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        result = await items.create_item(request, body, db)

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
    request = _request()
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
        result = await items.create_item(request, body, db)

    assert len(result.product.listings) == 1
    assert result.failed[0].url == "https://www.amazon.ca/dp/B0X"
    assert result.failed[0].detail == "Duplicate URL within this request"


@pytest.mark.asyncio
async def test_create_item_race_duplicate_url_returns_409() -> None:
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}):
        with pytest.raises(HTTPException) as exc_info:
            await items.create_item(request, body, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_without_urls_creates_product_with_no_listings() -> None:
    request = _request()
    db = MagicMock()
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Bare Product", target_price=10.0)

    with patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect:
        result = await items.create_item(request, body, db)

    detect.assert_not_awaited()
    assert result.product.name == "Bare Product"
    assert result.product.listings == []
    assert result.failed == []
    db.execute.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_listing_product_not_found_returns_404() -> None:
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with pytest.raises(HTTPException) as exc_info:
        await items.create_listing(request, 1, body, db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_listing_adds_to_existing_product() -> None:
    request = _request()
    product = _product(product_id=5)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _scalar_result(None)])
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with patch.dict("app.api.items.RETAILER_MAP", {"bestbuy.ca": object()}):
        result = await items.create_listing(request, 5, body, db)

    assert result.product_id == 5
    assert result.retailer == "bestbuy_ca"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_listing_duplicate_url_returns_409() -> None:
    request = _request()
    product = _product(product_id=5)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _scalar_result(1)])
    db.add = MagicMock()

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with pytest.raises(HTTPException) as exc_info:
        await items.create_listing(request, 5, body, db)

    assert exc_info.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_item_shortlink_resolves_before_retailer_map_routing(
    _stub_resolve_final_url: AsyncMock,
) -> None:
    # #39 — a shortlink's own hostname (a.co) would never match RETAILER_MAP;
    # routing must happen against the resolved destination's hostname.
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    _stub_resolve_final_url.side_effect = lambda url: "https://www.amazon.ca/dp/B0X"

    body = ProductCreate(name="Watch", target_price=10.0, urls=["https://a.co/d/abc"])

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()) as detect,
    ):
        result = await items.create_item(request, body, db)

    detect.assert_not_awaited()
    assert result.product.listings[0].url == "https://www.amazon.ca/dp/B0X"
    assert result.product.listings[0].retailer == "Amazon"
    assert result.failed == []


@pytest.mark.asyncio
async def test_create_listing_shortlink_resolves_before_retailer_map_routing(
    _stub_resolve_final_url: AsyncMock,
) -> None:
    request = _request()
    product = _product(product_id=5)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _scalar_result(None)])
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    _stub_resolve_final_url.side_effect = lambda url: "https://www.bestbuy.ca/p"

    body = ListingCreate(url="https://bby.link/xyz")

    with patch.dict("app.api.items.RETAILER_MAP", {"bestbuy.ca": object()}):
        result = await items.create_listing(request, 5, body, db)

    assert result.url == "https://www.bestbuy.ca/p"
    assert result.retailer == "bestbuy_ca"


@pytest.mark.asyncio
async def test_create_item_resolved_url_collision_within_batch_reported_in_failed(
    _stub_resolve_final_url: AsyncMock,
) -> None:
    # Two different pasted shortlinks resolving to the same real product —
    # the pre-resolve in-batch/DB dedup checks (against raw candidates)
    # can't catch this; must be re-checked post-resolve, and must degrade
    # per-URL rather than 409ing the whole batch (Listing.url is unique).
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    _stub_resolve_final_url.side_effect = lambda url: "https://www.amazon.ca/dp/B0X"

    body = ProductCreate(
        name="Item",
        target_price=10.0,
        urls=["https://a.co/d/one", "https://amzn.to/two"],
    )

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()),
    ):
        result = await items.create_item(request, body, db)

    assert len(result.product.listings) == 1
    assert result.product.listings[0].url == "https://www.amazon.ca/dp/B0X"
    assert len(result.failed) == 1
    assert result.failed[0].detail == "An item with this URL already exists"
    # Failure still echoes the URL the user actually pasted, not the
    # resolved one — same shape as every other failed[] entry.
    assert result.failed[0].url in ("https://a.co/d/one", "https://amzn.to/two")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_resolved_url_matches_existing_listing_reported_in_failed(
    _stub_resolve_final_url: AsyncMock,
) -> None:
    # Pasted shortlink resolves to a URL some other listing already tracks
    # directly — pre-resolve existing_urls check (against the raw shortlink)
    # can't catch this either; must be re-checked post-resolve.
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[_rows_result([]), _rows_result([("https://www.amazon.ca/dp/B0X",)])]
    )
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    _stub_resolve_final_url.side_effect = lambda url: "https://www.amazon.ca/dp/B0X"

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://a.co/d/one"])

    with (
        patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}),
        patch("app.api.items.detect_scraper_type", new=AsyncMock()),
    ):
        result = await items.create_item(request, body, db)

    assert result.product.listings == []
    assert result.failed[0].url == "https://a.co/d/one"
    assert result.failed[0].detail == "An item with this URL already exists"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_final_url_head_success_returns_final_url() -> None:
    resp = SimpleNamespace(status_code=200, url="https://www.amazon.ca/dp/B0X")
    client = _FakeHTTPClient(head=AsyncMock(return_value=resp))

    with patch("app.api.items.httpx.AsyncClient", return_value=client):
        result = await _real_resolve_final_url("https://a.co/d/abc")

    assert result == "https://www.amazon.ca/dp/B0X"
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_final_url_falls_back_to_get_on_head_error_status() -> None:
    head_resp = SimpleNamespace(status_code=405, url="https://a.co/d/abc")
    get_resp = SimpleNamespace(status_code=200, url="https://www.amazon.ca/dp/B0X")
    client = _FakeHTTPClient(
        head=AsyncMock(return_value=head_resp), get=AsyncMock(return_value=get_resp)
    )

    with patch("app.api.items.httpx.AsyncClient", return_value=client):
        result = await _real_resolve_final_url("https://a.co/d/abc")

    assert result == "https://www.amazon.ca/dp/B0X"
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_final_url_unchanged_when_no_redirect() -> None:
    resp = SimpleNamespace(status_code=200, url="https://shop.example.com/p")
    client = _FakeHTTPClient(head=AsyncMock(return_value=resp))

    with patch("app.api.items.httpx.AsyncClient", return_value=client):
        result = await _real_resolve_final_url("https://shop.example.com/p")

    assert result == "https://shop.example.com/p"


@pytest.mark.asyncio
async def test_resolve_final_url_falls_back_to_get_on_head_exception() -> None:
    # Some sites don't cleanly 4xx a HEAD they dislike — they drop the
    # connection or send a malformed response, which httpx surfaces as an
    # exception rather than a status code. Must still fall back to GET
    # before giving up, same as the status-code case.
    get_resp = SimpleNamespace(status_code=200, url="https://www.amazon.ca/dp/B0X")
    client = _FakeHTTPClient(
        head=AsyncMock(side_effect=httpx.RemoteProtocolError("boom")),
        get=AsyncMock(return_value=get_resp),
    )

    with patch("app.api.items.httpx.AsyncClient", return_value=client):
        result = await _real_resolve_final_url("https://a.co/d/abc")

    assert result == "https://www.amazon.ca/dp/B0X"
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_final_url_network_failure_raises_400() -> None:
    # Both HEAD and the GET fallback fail — genuinely unreachable.
    client = _FakeHTTPClient(
        head=AsyncMock(side_effect=httpx.ConnectError("boom")),
        get=AsyncMock(side_effect=httpx.ConnectError("boom")),
    )

    with patch("app.api.items.httpx.AsyncClient", return_value=client):
        with pytest.raises(HTTPException) as exc_info:
            await _real_resolve_final_url("https://dead-shortlink.example/x")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "URL could not be resolved"


@pytest.mark.asyncio
async def test_resolve_final_url_non_http_error_propagates_uncaught() -> None:
    # A bug in this function itself (not a network problem) should surface
    # as an unhandled exception (500), not get reported to the user as a
    # routing/resolution failure — the except clause is narrowed to
    # httpx.HTTPError specifically, not a bare `except Exception`.
    client = _FakeHTTPClient(head=AsyncMock(side_effect=RuntimeError("bug, not a network issue")))

    with patch("app.api.items.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError):
            await _real_resolve_final_url("https://shop.example.com/p")


@pytest.mark.asyncio
async def test_create_item_spawns_first_scrape_per_created_listing(
    _stub_first_scrape_dispatch: AsyncMock,
) -> None:
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(
        name="Multi",
        target_price=10.0,
        urls=["https://shop-a.example.com/p", "https://shop-b.example.com/p"],
    )

    with patch("app.api.items.detect_scraper_type", new=AsyncMock(return_value=None)):
        result = await items.create_item(request, body, db)

    listing_ids = {listing.id for listing in result.product.listings}
    dispatched_ids = {call.args[0] for call in _stub_first_scrape_dispatch.call_args_list}
    assert dispatched_ids == listing_ids
    for call in _stub_first_scrape_dispatch.call_args_list:
        assert call.args[1] is items._first_scrape_semaphore
        assert call.args[2] is request.app.state.event_queue


@pytest.mark.asyncio
async def test_create_item_does_not_spawn_for_failed_urls(
    _stub_first_scrape_dispatch: AsyncMock,
) -> None:
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Item", target_price=10.0, urls=["https://shop.example.com/p"])

    with patch(
        "app.api.items.detect_scraper_type",
        new=AsyncMock(side_effect=ValueError("URL not scrapable by any method")),
    ):
        result = await items.create_item(request, body, db)

    assert result.product.listings == []
    _stub_first_scrape_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_create_listing_spawns_first_scrape(
    _stub_first_scrape_dispatch: AsyncMock,
) -> None:
    request = _request()
    product = _product(product_id=5)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(product), _scalar_result(None)])
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ListingCreate(url="https://www.bestbuy.ca/p")

    with patch.dict("app.api.items.RETAILER_MAP", {"bestbuy.ca": object()}):
        result = await items.create_listing(request, 5, body, db)

    _stub_first_scrape_dispatch.assert_called_once_with(
        result.id, items._first_scrape_semaphore, request.app.state.event_queue
    )


@pytest.mark.asyncio
async def test_bounded_process_item_marks_error_on_unhandled_exception() -> None:
    listing = _listing(listing_id=7, last_scrape_status=None)
    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()

    with (
        patch("app.api.items.process_item", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.api.items.AsyncSessionLocal", return_value=_AsyncCM(session)),
    ):
        await _real_bounded_process_item(7, asyncio.Semaphore(1), asyncio.Queue())

    assert listing.last_scrape_status == "error"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bounded_process_item_does_not_overwrite_already_persisted_status() -> None:
    """A failure after process_item's own successful commit (e.g. in the
    trailing broadcast() call) must not stomp a real result back to
    'error'."""
    listing = _listing(listing_id=7, last_scrape_status="ok")
    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()

    with (
        patch("app.api.items.process_item", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.api.items.AsyncSessionLocal", return_value=_AsyncCM(session)),
    ):
        await _real_bounded_process_item(7, asyncio.Semaphore(1), asyncio.Queue())

    assert listing.last_scrape_status == "ok"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_bounded_process_item_missing_listing_does_not_raise() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()

    with (
        patch("app.api.items.process_item", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.api.items.AsyncSessionLocal", return_value=_AsyncCM(session)),
    ):
        await _real_bounded_process_item(7, asyncio.Semaphore(1), asyncio.Queue())  # must not raise

    session.commit.assert_not_awaited()


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
    request = _request()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_rows_result([]))
    db.add = MagicMock(side_effect=_assign_persisted_defaults)
    db.commit = AsyncMock()

    body = ProductCreate(name="Watch", target_price=10.0, urls=["https://www.amazon.ca/dp/B0X"])

    with patch.dict("app.api.items.RETAILER_MAP", {"amazon.ca": object()}):
        result = await items.create_item(request, body, db)

    assert len(result.product.listings) == 1
    assert result.product.listings[0].url == body.urls[0]
    assert result.failed == []
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_item_multiple_urls_probe_concurrently() -> None:
    request = _request()
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
        result = await items.create_item(request, body, db)

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
    request = _request()
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
        result = await items.create_item(request, body, db)  # must not raise

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
