import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.scheduler import jobs
from app.services import scrape_tracking
from app.services.scrape_tracking import in_flight_snapshot
from app.services.scraper.result import ScraperResult


@pytest.fixture(autouse=True)
def reset_in_flight_tracking():
    """Isolates every test in this file from scrape_tracking's module-level
    global set — a test that fails mid-assertion (before process_item's own
    finally would've run) could otherwise leak a marked listing id into the
    next test."""
    scrape_tracking._in_flight_listing_ids.clear()
    yield
    scrape_tracking._in_flight_listing_ids.clear()


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _listing(
    item_id: int = 1,
    *,
    retailer: str = "amazon_ca",
    product_id: int = 1,
    last_price: float | None = None,
    last_scrape_status: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id,
        url=f"https://example.com/item-{item_id}",
        retailer=retailer,
        scraper_type=None,
        product_id=product_id,
        last_price=last_price,
        last_scrape_status=last_scrape_status,
    )


def _product(
    product_id: int = 1,
    *,
    name="Item",
    target_price: float = 100.0,
    currency: str | None = None,
    alerted_at: dt.datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=product_id, name=name, target_price=target_price, currency=currency, alerted_at=alerted_at
    )


def _active_listings_result(listings: list[SimpleNamespace]) -> MagicMock:
    scalars = MagicMock()
    scalars.all.return_value = listings
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _scalar_result(value) -> MagicMock:
    """For process_item's column-only `select(Product.active)...` early
    check — a single-column result read via `.scalar_one_or_none()`, not
    `.scalars().all()` like `_active_listings_result` above."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _rows_result(rows: list[tuple]) -> MagicMock:
    """For poll_prices's `select(Listing.id, Listing.product_id)...` query —
    a multi-column result read via `.all()` (tuples), not `.scalars().all()`
    (single-column values) like the old flat `select(Listing.id)` used."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _product_result(product) -> MagicMock:
    """For process_item's locked `select(Product).where(...).with_for_update()`
    read (the alert-dedup race fix) — read via `.scalar_one()`, not
    `session.get(Product, ...)` like before the fix."""
    result = MagicMock()
    result.scalar_one.return_value = product
    return result


@pytest.mark.asyncio
async def test_poll_prices_processes_all_active_items() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_rows_result([(1, 1), (2, 1), (3, 1)]))

    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.RetailerRouter") as router_cls,
        patch("app.scheduler.jobs.process_item", new=AsyncMock()) as process_item,
    ):
        queue = asyncio.Queue()
        await jobs.poll_prices(queue)

    router = router_cls.return_value
    process_item.assert_any_await(1, router, queue)
    process_item.assert_any_await(2, router, queue)
    process_item.assert_any_await(3, router, queue)
    assert process_item.await_count == 3


@pytest.mark.asyncio
async def test_poll_prices_closes_browser_once_after_full_cycle() -> None:
    """close_if_idle() fires once, after the whole cycle — not per-product,
    not per-listing — so products/listings elsewhere in the cycle don't
    thrash open/close mid-cycle (#47), and so it fires after every product's
    concurrent batch has actually finished (#48), not mid-batch.

    All three listings here share one product (see the [(1, 1), (2, 1),
    (3, 1)] rows below), so they scrape concurrently under one gather() —
    call_order can't be asserted as a strict sequence any more (#48), only
    that "close" is last and every "process:N" happened before it."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=_rows_result([(1, 1), (2, 1), (3, 1)]))

    call_order: list[str] = []

    async def fake_process_item(item_id, router, queue):
        call_order.append(f"process:{item_id}")

    async def fake_close_if_idle():
        call_order.append("close")

    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.RetailerRouter"),
        patch("app.scheduler.jobs.process_item", new=AsyncMock(side_effect=fake_process_item)),
        patch(
            "app.scheduler.jobs.PatchrightScraper.close_if_idle",
            new=AsyncMock(side_effect=fake_close_if_idle),
        ) as mock_close,
    ):
        queue = asyncio.Queue()
        await jobs.poll_prices(queue)

    mock_close.assert_awaited_once()
    assert call_order[-1] == "close"
    assert set(call_order[:-1]) == {"process:1", "process:2", "process:3"}


@pytest.mark.asyncio
async def test_poll_prices_skips_when_lock_already_held() -> None:
    with (
        patch("app.scheduler.jobs.RetailerRouter") as router_cls,
        patch("app.scheduler.jobs.process_item", new=AsyncMock()) as process_item,
    ):
        async with jobs._prices_lock:
            queue = asyncio.Queue()
            await jobs.poll_prices(queue)

    router_cls.assert_not_called()
    process_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_prices_continues_when_item_processing_errors() -> None:
    """User-visible behavior unchanged post-#48 (all 3 items still get
    attempted despite one erroring) — but the mechanism that guarantees it
    moved: _bounded_process_item's own try/except now swallows the error
    before it ever reaches poll_prices' per-product try/except (see
    _bounded_process_item's docstring — it must never let an exception
    escape), so this is really exercising that backstop + gather()'s
    all-listings-run-regardless-of-one-failing behavior now, not
    poll_prices' own loop."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=_rows_result([(1, 1), (2, 1), (3, 1)]))

    process = AsyncMock(side_effect=[None, RuntimeError("boom"), None])
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.RetailerRouter") as router_cls,
        patch("app.scheduler.jobs.process_item", new=process),
    ):
        queue = asyncio.Queue()
        await jobs.poll_prices(queue)

    router = router_cls.return_value
    process.assert_any_await(1, router, queue)
    process.assert_any_await(2, router, queue)
    process.assert_any_await(3, router, queue)
    assert process.await_count == 3


@pytest.mark.asyncio
async def test_process_item_writes_history_and_price_drop_event() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    def _assign_event_id(obj):
        if obj.__class__.__name__ == "Event":
            obj.id = 55

    session.add = MagicMock(side_effect=_assign_event_id)

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert session.add.call_count == 2  # PriceHistory + Event
    assert listing.last_price == 90.0
    assert listing.last_scrape_status == "ok"
    assert product.alerted_at is not None
    session.commit.assert_awaited_once()
    assert await queue.get() == 55

    # The actual race-fix guard (issue #48), unit-asserted at the SQL level —
    # not simulated end-to-end. There's no `await` between the alerted_at
    # check and the write in process_item, so no mock-based interleaving can
    # ever demonstrate the real race in a single-threaded event loop: the
    # second task's resume is always processed strictly after the first's
    # completes, deterministically, regardless of locking (confirmed by
    # hand — a "no lock" version of this scenario still showed only one
    # alert firing, for the wrong reason). The lock's actual effect can only
    # be verified against a real Postgres serializing genuinely concurrent
    # transactions — see this issue's live-verification step, which the
    # correctness of *this* test doesn't substitute for. What's verifiable
    # here: process_item asks for the row lock, and does so exactly once
    # (not falling back to a plain, unlocked session.get(Product, ...)).
    assert session.get.await_count == 1  # only the Listing — no session.get(Product, ...)
    for_update_stmt = session.execute.call_args_list[1].args[0]
    assert for_update_stmt._for_update_arg is not None


@pytest.mark.asyncio
async def test_process_item_fills_retailer_when_still_hostname_fallback() -> None:
    """Issue #44 — _listing()'s URL is always https://example.com/item-N, so
    _derive_retailer(hostname) for it is always "Example" (generic-TLD
    strip, see router.py's _strip_tld_suffix). Constructing the listing
    with exactly that value simulates "untouched since creation" — the
    guard should fire."""
    listing = _listing(item_id=7, product_id=1, retailer="Example")
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok", site_name="Muddy George"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert listing.retailer == "Muddy George"


@pytest.mark.asyncio
async def test_process_item_does_not_overwrite_manually_edited_retailer() -> None:
    """A retailer that no longer matches the deterministic hostname fallback
    is treated as manually edited (PATCH .../listings/{id}) — must survive a
    scheduled poll finding a site_name, not get silently stomped."""
    listing = _listing(item_id=7, product_id=1, retailer="My Custom Name")
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok", site_name="Muddy George"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert listing.retailer == "My Custom Name"


@pytest.mark.asyncio
async def test_process_item_fills_product_name_when_null() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, name=None, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok", product_title="Cayl Cap Black"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert product.name == "Cayl Cap Black"


@pytest.mark.asyncio
async def test_process_item_does_not_overwrite_existing_product_name() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, name="User's Own Name", target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok", product_title="Cayl Cap Black"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert product.name == "User's Own Name"


@pytest.mark.asyncio
async def test_process_item_fills_product_currency_when_null() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, currency=None, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok", currency="KRW"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert product.currency == "KRW"


@pytest.mark.asyncio
async def test_process_item_does_not_overwrite_existing_product_currency() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, currency="USD", target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    # A re-scrape inferring a different currency (e.g. a flaky page read)
    # must never clobber a currency the user already has set/confirmed.
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok", currency="KRW"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert product.currency == "USD"


@pytest.mark.asyncio
async def test_process_item_marks_listing_in_flight_during_scrape() -> None:
    """Issue #45 follow-up — a re-scrape of an already-scraped listing
    previously had no "processing" signal at all (compute_status only knew
    about last_scrape_status is None, i.e. never-scraped-since-creation).
    Checked from inside the mocked scrape call itself, since that's the
    only window where it should be true — by the time process_item returns,
    it must be cleared again (asserted below)."""
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    seen_in_flight_during_scrape = False

    async def fake_get_price(*args, **kwargs) -> ScraperResult:
        nonlocal seen_in_flight_during_scrape
        seen_in_flight_during_scrape = 7 in in_flight_snapshot()
        return ScraperResult(price=90.0, status="ok")

    router = MagicMock()
    router.get_price = AsyncMock(side_effect=fake_get_price)

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert seen_in_flight_during_scrape is True
    assert in_flight_snapshot() == set()


@pytest.mark.asyncio
async def test_process_item_clears_in_flight_even_when_scraper_raises() -> None:
    """try/finally, not just the explicit oos/error/success returns — an
    unexpected exception from the scraper itself must not leave a listing
    permanently stuck showing "processing"."""
    listing = _listing(item_id=7, product_id=1)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.execute = AsyncMock(side_effect=[_scalar_result(True)])

    router = MagicMock()
    router.get_price = AsyncMock(side_effect=RuntimeError("scraper blew up"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        with pytest.raises(RuntimeError):
            await jobs.process_item(7, router, queue)

    assert in_flight_snapshot() == set()


@pytest.mark.asyncio
async def test_process_item_clears_in_flight_on_oos() -> None:
    listing = _listing(item_id=7, product_id=1)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True)])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status="oos"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(7, router, queue)

    assert in_flight_snapshot() == set()


@pytest.mark.asyncio
async def test_process_item_blocks_duplicate_drop_when_alerted() -> None:
    alerted = dt.datetime.now(dt.timezone.utc)
    listing = _listing(item_id=8, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=90.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(8, router, queue)

    assert session.add.call_count == 1  # PriceHistory only, no new Event (already alerted)
    assert product.alerted_at == alerted  # unchanged
    session.commit.assert_awaited_once()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_recovery_clears_alerted_at() -> None:
    alerted = dt.datetime.now(dt.timezone.utc)
    listing = _listing(item_id=9, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=120.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(9, router, queue)

    assert product.alerted_at is None
    assert session.add.call_count == 1
    session.commit.assert_awaited_once()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_excludes_oos_listing_stale_price_from_cheapest() -> None:
    """An 'oos' listing's last_price is frozen at whatever it was before it
    disappeared — it must not count toward the cheapest-active-listing
    comparison, or a phantom stale price could fire (or permanently hold
    open) an alert for a product that isn't actually purchasable there."""
    scraped = _listing(item_id=40, product_id=1, retailer="amazon_ca")
    oos_sibling = _listing(
        item_id=41,
        product_id=1,
        retailer="bestbuy_ca",
        last_price=50.0,
        last_scrape_status="oos",
    )
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=scraped)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([scraped, oos_sibling])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=150.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(40, router, queue)

    # Without the fix, oos_sibling's stale $50 would win and incorrectly
    # trigger (50 <= 100), even though nothing is actually available there.
    assert product.alerted_at is None
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_recovery_not_blocked_by_stale_oos_sibling() -> None:
    """The permanent-suppression form of the same bug: once alerted, a
    stale oos price must not prevent alerted_at from ever clearing, since
    that would silently block all future alerts for this product."""
    alerted = dt.datetime.now(dt.timezone.utc)
    scraped = _listing(item_id=50, product_id=1, retailer="amazon_ca")
    oos_sibling = _listing(
        item_id=51,
        product_id=1,
        retailer="bestbuy_ca",
        last_price=50.0,
        last_scrape_status="oos",
    )
    product = _product(product_id=1, target_price=100.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(return_value=scraped)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([scraped, oos_sibling])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=150.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(50, router, queue)

    # Without the fix, oos_sibling's stale $50 would keep "cheapest" <= 100
    # forever, so alerted_at would never clear even though the only
    # available listing has recovered to $150.
    assert product.alerted_at is None
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_unrelated_active_listing_does_not_incorrectly_rearm() -> None:
    """The bug this rewrite exists to prevent: BestBuy already triggered the
    alert at $340 (target $350). Amazon's own routine poll comes back at
    $398 (unchanged, still above target) — that must NOT clear the product's
    alerted_at, since the product is still a deal via BestBuy."""
    alerted = dt.datetime.now(dt.timezone.utc)
    amazon = _listing(item_id=30, product_id=1, retailer="amazon_ca", last_price=398.0)
    bestbuy = _listing(item_id=31, product_id=1, retailer="bestbuy_ca", last_price=340.0, last_scrape_status="ok")
    product = _product(product_id=1, target_price=350.0, alerted_at=alerted)

    session = MagicMock()
    session.get = AsyncMock(return_value=amazon)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([amazon, bestbuy])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=398.0, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(30, router, queue)

    assert product.alerted_at == alerted  # still armed — BestBuy is still under target
    assert queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["oos", "error"])
async def test_process_item_persists_scrape_status_on_oos_or_error(status: str) -> None:
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_scalar_result(True))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status=status))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(10, router, queue)

    assert listing.last_scrape_status == status
    session.add.assert_not_called()  # no PriceHistory row — no price to record
    session.commit.assert_awaited_once()  # but the status write is persisted
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_skips_ok_status_with_none_price() -> None:
    """Anomalous combination (status=ok but no price) — nothing meaningful
    happened, so nothing is written at all, unlike oos/error."""
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_scalar_result(True))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status="ok"))

    queue = asyncio.Queue()
    with patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)):
        await jobs.process_item(10, router, queue)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_item_broadcasts_after_successful_scrape() -> None:
    listing = _listing(item_id=7, product_id=1)
    product = _product(product_id=1, target_price=100.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([listing])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=120.0, status="ok"))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs.process_item(7, router, queue)

    broadcast_mock.assert_called_once_with({"product_id": 1, "listing_id": 7})


@pytest.mark.asyncio
async def test_process_item_broadcast_uses_scraped_listing_not_cheapest_winner() -> None:
    """Regression: the broadcast must carry the listing that was actually
    scraped (item 7), not `winning` (the alert Event's cheapest-listing
    field) — those differ whenever a sibling retailer is cheaper."""
    scraped = _listing(item_id=7, product_id=1, retailer="amazon_ca")
    cheaper_sibling = _listing(item_id=8, product_id=1, retailer="bestbuy_ca", last_price=50.0, last_scrape_status="ok")
    product = _product(product_id=1, target_price=200.0, alerted_at=None)

    session = MagicMock()
    session.get = AsyncMock(return_value=scraped)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(side_effect=[_scalar_result(True), _product_result(product), _active_listings_result([scraped, cheaper_sibling])])

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=180.0, status="ok"))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs.process_item(7, router, queue)

    broadcast_mock.assert_called_once_with({"product_id": 1, "listing_id": 7})  # not 8


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["oos", "error"])
async def test_process_item_does_not_broadcast_on_oos_or_error(status: str) -> None:
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_scalar_result(True))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status=status))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs.process_item(10, router, queue)

    broadcast_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_item_does_not_broadcast_when_ok_status_has_none_price() -> None:
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_scalar_result(True))

    router = MagicMock()
    router.get_price = AsyncMock(return_value=ScraperResult(price=None, status="ok"))

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs.process_item(10, router, queue)

    broadcast_mock.assert_not_called()


@pytest.mark.asyncio
async def test_process_item_does_not_broadcast_for_an_inactive_product() -> None:
    """Pause/resume is product-level only (issue #48) — process_item's early
    bail is now a column-only Product.active check, not listing.active."""
    listing = _listing(item_id=10)

    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.execute = AsyncMock(return_value=_scalar_result(False))

    router = MagicMock()
    router.get_price = AsyncMock()

    queue = asyncio.Queue()
    with (
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
        patch("app.scheduler.jobs.broadcast") as broadcast_mock,
    ):
        await jobs.process_item(10, router, queue)

    router.get_price.assert_not_called()
    broadcast_mock.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_first_scrapes_closes_browser_once_batch_drains() -> None:
    """_dispatch_first_scrapes() waits for every listing in its own batch to
    finish, then closes the shared Patchright browser once close_if_idle()
    confirms the global _active_scrapes is back to 0 — proving a real
    teardown, not a no-op, via a changed _context identity on next use.

    Moved here from tests/api/test_items_routes.py (issue #48) alongside
    _bounded_process_item/_dispatch_first_scrapes themselves — both #41's
    add-time dispatch (items.py) and poll_prices's per-product dispatch
    (this file) now share this one implementation."""
    call_order: list[str] = []

    async def fake_bounded(listing_id, semaphore, queue):
        call_order.append(f"process:{listing_id}")

    async def fake_close_if_idle():
        call_order.append("close")

    with (
        patch("app.scheduler.jobs._bounded_process_item", new=AsyncMock(side_effect=fake_bounded)),
        patch(
            "app.scheduler.jobs.PatchrightScraper.close_if_idle",
            new=AsyncMock(side_effect=fake_close_if_idle),
        ) as mock_close,
    ):
        await jobs._dispatch_first_scrapes([1, 2, 3], asyncio.Semaphore(3), asyncio.Queue())

    mock_close.assert_awaited_once()
    assert call_order[-1] == "close"  # only after every listing in the batch finished
    assert {"process:1", "process:2", "process:3"} == set(call_order[:-1])


@pytest.mark.asyncio
async def test_dispatch_first_scrapes_does_not_close_when_other_scrape_still_in_flight() -> None:
    """A second, unrelated batch still holding the global _active_scrapes
    above 0 must survive this batch's own drain-and-check — close_if_idle()
    checks the shared counter, not a per-request local one."""
    from app.services.scraper.patchright_scraper import PatchrightScraper

    original_active_scrapes = PatchrightScraper._active_scrapes
    PatchrightScraper._active_scrapes = 1  # simulate an unrelated in-flight scrape
    try:
        with (
            patch("app.scheduler.jobs._bounded_process_item", new=AsyncMock()),
            patch.object(PatchrightScraper, "close_browser", new=AsyncMock()) as mock_close,
        ):
            await jobs._dispatch_first_scrapes([1], asyncio.Semaphore(1), asyncio.Queue())
        mock_close.assert_not_awaited()
    finally:
        PatchrightScraper._active_scrapes = original_active_scrapes


@pytest.mark.asyncio
async def test_bounded_process_item_marks_error_on_unhandled_exception() -> None:
    listing = _listing(item_id=7, last_scrape_status=None)
    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()

    with (
        patch("app.scheduler.jobs.process_item", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
    ):
        await jobs._bounded_process_item(7, asyncio.Semaphore(1), asyncio.Queue())

    assert listing.last_scrape_status == "error"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bounded_process_item_does_not_overwrite_already_persisted_status() -> None:
    """A failure after process_item's own successful commit (e.g. in the
    trailing broadcast() call) must not stomp a real result back to
    'error'."""
    listing = _listing(item_id=7, last_scrape_status="ok")
    session = MagicMock()
    session.get = AsyncMock(return_value=listing)
    session.commit = AsyncMock()

    with (
        patch("app.scheduler.jobs.process_item", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
    ):
        await jobs._bounded_process_item(7, asyncio.Semaphore(1), asyncio.Queue())

    assert listing.last_scrape_status == "ok"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_bounded_process_item_missing_listing_does_not_raise() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()

    with (
        patch("app.scheduler.jobs.process_item", new=AsyncMock(side_effect=RuntimeError("boom"))),
        patch("app.scheduler.jobs.AsyncSessionLocal", return_value=_AsyncCM(session)),
    ):
        await jobs._bounded_process_item(7, asyncio.Semaphore(1), asyncio.Queue())  # must not raise

    session.commit.assert_not_awaited()


def _finnhub_mock(tickers: list[str], prices: dict[str, float | None]) -> MagicMock:
    finnhub = MagicMock()
    finnhub.cached_tickers.return_value = tickers
    finnhub.get_price = AsyncMock(side_effect=lambda t: prices.get(t))
    finnhub.check_threshold = AsyncMock()
    return finnhub


@pytest.mark.asyncio
async def test_poll_stocks_checks_all_cached_tickers() -> None:
    finnhub = _finnhub_mock(["AAPL", "TSLA"], {"AAPL": 150.0, "TSLA": 200.0})

    await jobs.poll_stocks(finnhub)

    finnhub.check_threshold.assert_any_await("AAPL", 150.0)
    finnhub.check_threshold.assert_any_await("TSLA", 200.0)
    assert finnhub.check_threshold.await_count == 2


@pytest.mark.asyncio
async def test_poll_stocks_skips_ticker_with_none_price() -> None:
    finnhub = _finnhub_mock(["AAPL"], {"AAPL": None})

    await jobs.poll_stocks(finnhub)

    finnhub.check_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_stocks_continues_when_ticker_processing_errors() -> None:
    finnhub = MagicMock()
    finnhub.cached_tickers.return_value = ["AAPL", "TSLA"]
    finnhub.get_price = AsyncMock(side_effect=[RuntimeError("boom"), 200.0])
    finnhub.check_threshold = AsyncMock()

    await jobs.poll_stocks(finnhub)

    finnhub.check_threshold.assert_awaited_once_with("TSLA", 200.0)


@pytest.mark.asyncio
async def test_poll_stocks_skips_when_lock_already_held() -> None:
    finnhub = _finnhub_mock(["AAPL"], {"AAPL": 150.0})

    async with jobs._stocks_lock:
        await jobs.poll_stocks(finnhub)

    finnhub.cached_tickers.assert_not_called()
    finnhub.check_threshold.assert_not_awaited()
