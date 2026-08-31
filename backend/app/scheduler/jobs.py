import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models.event import Event
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.watch_item import Listing
from app.services.fx import refresh_fx_rates
from app.services.scrape_tracking import clear_in_flight, mark_in_flight
from app.services.scraper.patchright_scraper import PatchrightScraper
from app.services.scraper.router import RetailerRouter, _derive_retailer, _hostname_of
from app.services.sse import broadcast
from app.services.stocks import FinnhubClient

_log = logging.getLogger(__name__)

_prices_lock = asyncio.Lock()
_stocks_lock = asyncio.Lock()
_fx_lock = asyncio.Lock()

# Bounds how many of poll_prices's per-product listings scrape concurrently.
# Same value as items.py's _FIRST_SCRAPE_CONCURRENCY (#41), deliberately a
# separate instance, not a shared pool: an add-time burst (items.py) and a
# scheduled poll_prices cycle can genuinely overlap in time, and sharing one
# pool would let an add-time request wait behind poll_prices's own slots,
# adding latency to a user-facing action.
_POLL_CONCURRENCY = 3
_poll_concurrency_semaphore = asyncio.Semaphore(_POLL_CONCURRENCY)


async def poll_prices(queue: asyncio.Queue) -> None:
    if _prices_lock.locked():
        _log.warning("poll_prices: skipping — previous cycle still running")
        return

    async with _prices_lock:
        _log.info("poll_prices: starting cycle")

        async with AsyncSessionLocal() as session:
            # Pause/resume is product-level only (issue #48) — Listing has
            # no active column of its own, so this joins Product to filter.
            result = await session.execute(
                select(Listing.id, Listing.product_id)
                .join(Product, Listing.product_id == Product.id)
                .where(Product.active == True)  # noqa: E712
            )
            rows = result.all()

        # Grouped by product, not the old flat/unordered list — a product's
        # own listings are scraped together, and now concurrently (bounded,
        # same gather-with-semaphore shape as #41's add-time dispatch — see
        # _gather_bounded_scrapes), instead of scattered across the cycle
        # purely as a side effect of query order having nothing to do with
        # product grouping. Products themselves are still processed one
        # after another (dict preserves insertion order — no ORDER BY
        # needed), preserving _prices_lock's whole-cycle serialization
        # guarantee.
        listings_by_product: dict[int, list[int]] = {}
        for listing_id, product_id in rows:
            listings_by_product.setdefault(product_id, []).append(listing_id)

        item_count = sum(len(listing_ids) for listing_ids in listings_by_product.values())
        _log.info("poll_prices: %d active items across %d products", item_count, len(listings_by_product))

        for product_id, listing_ids in listings_by_product.items():
            try:
                # Backstop, not the primary error path — _bounded_process_item
                # never lets an exception escape (see its own docstring), so
                # in practice this except only guards against gather() itself
                # misbehaving, not a listing-level scrape/DB failure.
                await _gather_bounded_scrapes(listing_ids, _poll_concurrency_semaphore, queue)
            except Exception:
                _log.error("poll_prices: unhandled error for product %d", product_id, exc_info=True)

        # End-of-cycle close, not per-product — calling _gather_bounded_scrapes
        # directly (not _dispatch_first_scrapes, which bundles its own
        # close_if_idle() per call) is what keeps this to exactly one close
        # for the whole cycle instead of one per product, which would thrash
        # open/close between products for no benefit. close_if_idle() (not
        # close_browser() directly) since an ad-hoc #41 add-time batch can
        # genuinely be running concurrently on the same event loop.
        await PatchrightScraper.close_if_idle()

        _log.info("poll_prices: cycle complete")


async def poll_stocks(finnhub: FinnhubClient) -> None:
    if _stocks_lock.locked():
        _log.warning("poll_stocks: skipping — previous cycle still running")
        return

    async with _stocks_lock:
        tickers = finnhub.cached_tickers()
        _log.info("poll_stocks: re-checking %d cached ticker(s)", len(tickers))

        for ticker in tickers:
            try:
                price = await finnhub.get_price(ticker)
                if price is not None:
                    await finnhub.check_threshold(ticker, price)
            except Exception:
                _log.error("poll_stocks: unhandled error for %s", ticker, exc_info=True)

        _log.info("poll_stocks: cycle complete")


async def refresh_fx_rates_job() -> None:
    """Issue #45 — scheduled wrapper around services.fx.refresh_fx_rates,
    opening its own session same as poll_prices/poll_stocks (the scheduler
    doesn't hand jobs a session). Registered `"interval", hours=24,
    next_run_time=datetime.now(_TZ)` in main.py's lifespan — fires
    immediately at every boot, then every 24h from that boot time, not
    anchored to midnight (matches poll_prices's existing registration, the
    only other scheduled job in this codebase)."""
    if _fx_lock.locked():
        _log.warning("refresh_fx_rates_job: skipping — previous run still in progress")
        return

    async with _fx_lock:
        async with AsyncSessionLocal() as session:
            await refresh_fx_rates(session)


async def process_item(item_id: int, router: RetailerRouter, queue: asyncio.Queue) -> None:
    async with AsyncSessionLocal() as session:
        listing = await session.get(Listing, item_id)
        if not listing:
            return

        # Pause/resume is product-level only (issue #48) — a column-only
        # select, not session.get(Product, ...), deliberately: this must not
        # populate the session's identity map ahead of the later
        # with_for_update() Product read below (used for the alert-dedup
        # check) — if it did, that locked read could hand back this earlier,
        # pre-lock instance instead of a genuinely fresh one, silently
        # reintroducing the double-alert race this issue exists to fix, just
        # relocated. See .plan/48-.../schema.md and challenges.md #4.
        product_active = (
            await session.execute(select(Product.active).where(Product.id == listing.product_id))
        ).scalar_one_or_none()
        if product_active is not True:
            return

        # Marked in flight (issue #45 follow-up) from right before the scrape
        # itself through every exit path below (try/finally, not just the
        # explicit returns — an unexpected exception anywhere in here must
        # still clear it, or this listing would show "processing" forever).
        # compute_status() checks this so a re-scrape of an already-scraped
        # listing (scheduled poll_prices, or a manual POST /api/poll/prices)
        # shows "processing" too — previously only "never scraped since
        # creation" (last_scrape_status is None) had any processing signal
        # at all, so re-scraping an existing listing looked identical to
        # doing nothing until the new result landed.
        mark_in_flight(listing.id)
        # Issue #51 follow-up — a "started" broadcast, mirroring the
        # completion one below, so compute_status()'s "processing" signal
        # (issue #45 follow-up, docstring above) is actually observable
        # client-side. Without this, nothing tells a connected frontend to
        # refetch until the scrape's own completion broadcast fires — by
        # which point in_flight has already cleared, so "processing" is
        # never visible for a scrape too fast to be caught by some *other*
        # listing's completion refetch landing while this one's still mid-
        # flight (the only way it was ever visible before: reliably true
        # for poll_prices's own many-listings-at-once cycle, effectively
        # never true for a single-listing manual per-item poll).
        broadcast({"product_id": listing.product_id, "listing_id": listing.id})
        try:
            scrape = await router.get_price(listing.url, scraper_type=listing.scraper_type)

            if scrape.status == "oos":
                _log.info("listing %d (%s) out of stock", listing.id, listing.retailer)
                listing.last_scrape_status = "oos"
                await session.commit()
                return

            if scrape.status == "error":
                _log.warning("scraper error for listing %d (%s)", listing.id, listing.retailer)
                listing.last_scrape_status = "error"
                await session.commit()
                return

            if scrape.price is None:
                _log.warning(
                    "scraper returned ok with None price for listing %d (%s), skipping",
                    listing.id,
                    listing.retailer,
                )
                return

            now = datetime.now(timezone.utc)
            session.add(PriceHistory(watch_item_id=listing.id, price=scrape.price))
            listing.last_price = scrape.price
            listing.last_scrape_status = "ok"

            # Retailer-name inference (issue #44) — guarded: only overwrite while
            # listing.retailer still equals what _derive_retailer(hostname) would
            # produce right now, i.e. untouched since creation. A user's manual
            # edit (PATCH .../listings/{id}) no longer matches that deterministic
            # fallback, so it's left alone — this is what stops a scheduled poll
            # 6h later from silently stomping it. Doesn't need `product` at all,
            # so it happens here rather than at the locked read below.
            if scrape.site_name:
                hostname = _hostname_of(listing.url)
                if listing.retailer == _derive_retailer(hostname):
                    listing.retailer = scrape.site_name

            # Locked read (issue #48) — two listings of the same product scraped
            # concurrently (see _poll_concurrency_semaphore / #41's own
            # concurrent add-time dispatch) each open their own session here.
            # Without the lock, both could read alerted_at as None before either
            # commits, and both fire — a double alert for one price drop. Postgres
            # blocks the second transaction at this line until the first commits,
            # so the second one's read below is guaranteed fresh, not raced.
            # Acquired after the scrape (network I/O) already completed, so this
            # only serializes the short tail (this read through the commit
            # below), not the slow part #48's concurrency exists to speed up.
            product = (
                await session.execute(select(Product).where(Product.id == listing.product_id).with_for_update())
            ).scalar_one()

            # Product-name inference (issue #44) — guarded: only while still
            # NULL (the user left it blank at creation and nothing has filled it
            # yet). Piggybacks on the locked read just above rather than a
            # separate query — this fill isn't itself race-sensitive, but the
            # row's already open here for #48's alert-dedup fix, so no reason to
            # pay for a second fetch.
            if scrape.product_title and product.name is None:
                product.name = scrape.product_title

            # Currency inference (issue #45) — same guard as product-name
            # inference just above, same locked row, no extra query. In
            # practice this fires on a product's first successful scrape:
            # _extract_currency always resolves to a concrete value (CAD
            # default) rather than None, so scrape.currency is truthy on
            # essentially every status="ok" scrape reaching this point.
            if scrape.currency and product.currency is None:
                product.currency = scrape.currency

            product_listings_result = await session.execute(select(Listing).where(Listing.product_id == product.id))
            product_listings = list(product_listings_result.scalars().all())
            # Only listings confirmed available ("ok") are eligible — an "oos"
            # listing's last_price is frozen at whatever it was before it
            # disappeared, and letting that stale price win the comparison would
            # make it permanently block future alerts (it can never be beaten,
            # so alerted_at would never clear even after it recovers elsewhere).
            # The just-scraped `listing` is always "ok" here, so this is never empty.
            available_listings = [l for l in product_listings if l.last_price is not None and l.last_scrape_status == "ok"]
            winning = min(available_listings, key=lambda l: l.last_price)
            cheapest = winning.last_price

            if cheapest <= product.target_price and product.alerted_at is None:
                event = Event(
                    type="PRICE_DROP",
                    payload={
                        "product_id": product.id,
                        "listing_id": winning.id,
                        "retailer": winning.retailer,
                        "price": cheapest,
                        "url": winning.url,
                    },
                    status="pending",
                )
                session.add(event)
                product.alerted_at = now
                await session.commit()
                await queue.put(event.id)
                _log.info(
                    "PRICE_DROP: product %d (%s) @ %.2f (target %.2f) via %s",
                    product.id,
                    product.name,
                    cheapest,
                    product.target_price,
                    winning.retailer,
                )
            elif cheapest > product.target_price and product.alerted_at is not None:
                product.alerted_at = None
                await session.commit()
                _log.info("product %d (%s) re-armed (price recovered)", product.id, product.name)
            else:
                await session.commit()

            # Unconditional — fires on every successful scrape regardless of price
            # change, as a sibling to the alert-only Event/queue write above, not
            # a consumer of it. Placed after all three commit branches (not right
            # after the PriceHistory insert) so the broadcast never fires ahead of
            # the transaction that's supposed to have already persisted it.
            broadcast({"product_id": product.id, "listing_id": listing.id})
        finally:
            clear_in_flight(listing.id)


async def _bounded_process_item(listing_id: int, semaphore: asyncio.Semaphore, queue: asyncio.Queue) -> None:
    """Runs process_item under a caller-supplied concurrency bound. Shared by
    two callers on different lifecycles: #41's add-time first-scrape (spawned
    via spawn() in items.py, called from a request handler — outlives the
    request/response cycle that triggered it, see .doc/keynotes.md's asyncio
    concurrency section for why spawn() itself needs no reference-holding
    help there, it already keeps one via _background_tasks) and poll_prices's
    per-product scheduled scrape below (called directly, awaited as part of
    the cycle). A fresh RetailerRouter per call is deliberate, not a corner
    cut — it's stateless (no __init__), so there's nothing to share by
    reusing one across concurrent calls.

    Must never let an exception escape — items.py's caller runs this inside a
    detached asyncio.Task (see spawn()); an unhandled exception there doesn't
    crash anything visibly, it just becomes an "exception was never
    retrieved" warning while the listing is stuck at
    last_scrape_status=None (reads as permanently "Processing" in the UI)
    until the next scheduled poll_prices cycle happens to retry it, up to 6h
    later, same failure mode trading_agents.py's run_analysis already guards
    against for the same reason. process_item's own scraper calls already
    catch realistic failures and return status="error" — this is the
    backstop for what's left (a DB hiccup, an unexpected bug), so it only
    writes "error" if the listing is still unscraped, never stomping a
    status process_item itself already committed (e.g. if the failure were
    in the trailing broadcast() call, after a real successful scrape+commit).
    """
    async with semaphore:
        try:
            await process_item(listing_id, RetailerRouter(), queue)
        except Exception:
            _log.error("bounded scrape failed for listing %d", listing_id, exc_info=True)
            try:
                async with AsyncSessionLocal() as session:
                    listing = await session.get(Listing, listing_id)
                    if listing is not None and listing.last_scrape_status is None:
                        listing.last_scrape_status = "error"
                        await session.commit()
            except Exception:
                _log.error(
                    "bounded scrape: failed to persist error status for listing %d",
                    listing_id,
                    exc_info=True,
                )


async def _gather_bounded_scrapes(listing_ids: list[int], semaphore: asyncio.Semaphore, queue: asyncio.Queue) -> None:
    """gather()s every listing in listing_ids under the given semaphore — the
    gather() alone, deliberately split out from _dispatch_first_scrapes'
    close_if_idle() below. poll_prices calls this directly, once per
    *product*, but wants close_if_idle() only once per whole *cycle* (after
    every product's batch), not once per product — the split is what makes
    that possible without poll_prices reaching into _dispatch_first_scrapes'
    internals. _bounded_process_item never raises (see its own docstring),
    so no return_exceptions=True is needed here — that "never raises"
    contract is load-bearing, not just an optimization: gather() doesn't
    auto-cancel sibling tasks when one of them raises, so if that contract
    were ever violated, an early failure here could leave the rest of this
    product's own listings (or, in #41's case, this request's own batch)
    silently abandoned mid-scrape rather than merely logged and skipped."""
    await asyncio.gather(*(_bounded_process_item(lid, semaphore, queue) for lid in listing_ids))


async def _dispatch_first_scrapes(listing_ids: list[int], semaphore: asyncio.Semaphore, queue: asyncio.Queue) -> None:
    """One background task per *request* — #41's add-time first-scrape,
    spawned by create_item/create_listing to gather() every listing in this
    request's own batch (via _gather_bounded_scrapes above), then close the
    shared Patchright browser once it's confirmed idle. close_if_idle() (not
    close_browser() directly) checks the *global* _active_scrapes, not a
    per-caller count — that's what makes this safe against an unrelated
    request's own batch, or a poll_prices product's own batch (see
    _gather_bounded_scrapes), still running concurrently on the same event
    loop: its scrapes keep the shared counter above 0, so this call
    correctly skips closing. No debounce/timer needed — gather() only
    returns once every listing in this specific batch has finished, so
    there's no "maybe one more from the same batch" case left to guard
    against."""
    await _gather_bounded_scrapes(listing_ids, semaphore, queue)
    await PatchrightScraper.close_if_idle()
