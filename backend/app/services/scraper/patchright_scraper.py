import asyncio
import logging
import os
import re
import tempfile

from bs4 import BeautifulSoup
from patchright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.services.scraper.base import BaseScraper, _describe_exception, _parse_price
from app.services.scraper.config import (
    AMAZON_MAX_RETRIES,
    CLOUDFLARE_CHALLENGE_TIMEOUT_MS,
    PAGE_NAV_TIMEOUT_MS,
    PRICE_LOCATOR_TIMEOUT_MS,
)
from app.services.scraper.result import ScraperResult

_log = logging.getLogger(__name__)

_USER_DATA_DIR = os.path.join(tempfile.gettempdir(), "patchright-profile")

# Virtual display Chromium renders into (#15). X11 lock files store the
# holder's PID as plain ASCII text at this well-known path per display
# number — used by _xvfb_already_running() below to tell a genuinely
# live Xvfb apart from a stale lock left by a process that died without
# cleaning up (e.g. a crashed prior run).
_XVFB_DISPLAY = ":99"
_XVFB_LOCK_FILE = "/tmp/.X99-lock"


def _read_proc_comm(pid: int) -> str | None:
    """Reads /proc/{pid}/comm — the OS's own record of what a PID's process
    is actually named. Isolated into its own module-level function (rather
    than inlined) so tests can patch it directly — this dev project's Mac
    environment has no /proc filesystem at all to read from for real."""
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return None


class PatchrightScraper(BaseScraper):
    _playwright: Playwright | None = None
    _browser: Browser | None = None
    _context: BrowserContext | None = None
    # Guards start_browser() against concurrent launches — see [[Locks (Mutexes)]]
    # in .doc/keynotes.md. Safe to construct here at class-definition time: since
    # Python 3.10, asyncio.Lock() no longer binds to an event loop at construction,
    # only lazily on first real use inside a running loop.
    _start_lock: asyncio.Lock = asyncio.Lock()
    # Counts scrapes currently mid-flight (between new_page() and page.close()),
    # incremented/decremented around every get_price() call site. close_if_idle()
    # checks this to avoid closing the context out from under an in-flight scrape.
    _active_scrapes: int = 0
    # Virtual display Chromium renders into (#15) — Pi OS Lite has no real X11/
    # Wayland server, and headless Chromium gets detected/blocked by BestBuy
    # (Akamai) and SSENSE (Cloudflare+Riskified). Deliberately decoupled from
    # _context's lifecycle: Xvfb holds no session state that goes stale the way
    # a browser context does, so it must NOT restart on close_if_idle()'s much
    # more frequent cycle — only start_browser() (lazy start) and stop_xvfb()
    # (real app shutdown only, see main.py's lifespan) ever touch this.
    _xvfb_process: asyncio.subprocess.Process | None = None

    @staticmethod
    def _clear_stale_xvfb_lock() -> None:
        try:
            os.remove(_XVFB_LOCK_FILE)
        except FileNotFoundError:
            pass

    @staticmethod
    def _xvfb_already_running() -> bool:
        """True if some Xvfb process we don't ourselves track (_xvfb_process
        is process-local memory, so it doesn't survive across separate
        process invocations — e.g. a standalone script run twice against
        the same long-lived container) already holds the display lock and
        is genuinely alive. A stale lock left by a process that died
        without cleaning up is detected and removed here instead, so a
        fresh Xvfb can actually start rather than refusing to bind.

        File I/O here is deliberately kept synchronous rather than wrapped
        in run_in_executor() — the reads involved (a few bytes from a lock
        file, a /proc entry) are fast enough that dispatching to a thread
        pool would cost more than the blocking call itself; this runs while
        _start_lock is held, so the brief stall is a stated trade-off, not
        an oversight."""
        try:
            with open(_XVFB_LOCK_FILE) as f:
                pid = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return False  # no lock file, or unreadable — nothing running
        if pid <= 0:
            # os.kill(0, 0) signals our own process group, not a specific
            # PID — never a value Xvfb itself would write, but guard
            # against a malformed lock spuriously reporting "alive" anyway.
            return False
        try:
            os.kill(pid, 0)  # signal 0: existence check only, doesn't kill
        except ProcessLookupError:
            # Stale — the process that held this lock is gone. Clean it up
            # so Xvfb's own startup doesn't refuse to bind on our behalf.
            PatchrightScraper._clear_stale_xvfb_lock()
            return False
        except PermissionError:
            pass  # exists, just owned by another user — confirm identity below
        # The PID exists, but over this app's days/weeks of continuous
        # uptime the OS can reassign a dead Xvfb's old PID to an unrelated
        # process (if Xvfb ever died without cleaning up its own lock —
        # e.g. a hard kill, not close_browser()'s normal .terminate()).
        # Confirm the live process is actually Xvfb before trusting it.
        if _read_proc_comm(pid) != "Xvfb":
            PatchrightScraper._clear_stale_xvfb_lock()
            return False
        return True

    @classmethod
    async def start_browser(cls) -> None:
        if cls._context is not None:
            return
        async with cls._start_lock:
            if cls._context is not None:  # re-check — another caller may have won the race
                return
            try:
                if cls._xvfb_process is None or cls._xvfb_process.returncode is not None:
                    # Not tracked as running in *this* process's memory — but
                    # something else (an orphan from an earlier crashed run,
                    # e.g. a standalone script invoked more than once against
                    # the same container) may still genuinely hold the
                    # display. Only spawn a fresh one if nothing real is
                    # actually using it; otherwise just reuse it.
                    if not cls._xvfb_already_running():
                        # asyncio's own subprocess spawn, not the blocking
                        # subprocess module — matches this codebase's
                        # existing convention for child processes
                        # (trading_agents.py, analysis.py both use
                        # asyncio.create_subprocess_exec).
                        cls._xvfb_process = await asyncio.create_subprocess_exec(
                            "Xvfb", _XVFB_DISPLAY, "-screen", "0", "1920x1080x24"
                        )
                    # DISPLAY must be set before launch_persistent_context()
                    # below so Chromium knows which display to connect to,
                    # whether we just spawned Xvfb or are reusing one.
                    os.environ["DISPLAY"] = _XVFB_DISPLAY

                executable_path = os.environ.get("CHROMIUM_PATH")
                cls._playwright = await async_playwright().start()
                # Persistent context: cookies/localStorage survive across pages in a run,
                # making the session look like a returning user to bot detectors.
                cls._context = await cls._playwright.chromium.launch_persistent_context(
                    _USER_DATA_DIR,
                    # Genuinely headed (into the Xvfb virtual display above), not
                    # headless (#15) — both BestBuy and SSENSE block headless
                    # Chromium specifically; confirmed via live testing that a
                    # real headed browser passes both cleanly, same TLS stack.
                    headless=False,
                    **({"executable_path": executable_path} if executable_path else {}),
                    locale="en-CA",
                    timezone_id="America/Toronto",
                )
                cls._browser = None  # not used directly; pages come from _context
            except Exception:
                # Launch failed partway (e.g. after the driver started but before
                # the context finished) — clean up rather than leaving an
                # orphaned driver process for the next attempt's own
                # `async_playwright().start()` to silently overwrite and leak.
                if cls._playwright:
                    await cls._playwright.stop()
                cls._playwright = None
                cls._context = None
                raise

    @classmethod
    async def close_browser(cls) -> None:
        if cls._context:
            await cls._context.close()
        if cls._playwright:
            await cls._playwright.stop()
        cls._browser = None
        cls._context = None
        cls._playwright = None

    @classmethod
    async def stop_xvfb(cls) -> None:
        """Kills the Xvfb subprocess (#15) — called exactly once in the whole
        app, from main.py's lifespan real-shutdown block, never from
        close_browser()/close_if_idle(). Xvfb has no session state to
        protect against concurrent access the way _context does, and this
        only ever runs after everything else has already stopped using the
        browser, so no lock is needed here unlike close_if_idle()."""
        if cls._xvfb_process is not None:
            cls._xvfb_process.terminate()
            await cls._xvfb_process.wait()
            cls._xvfb_process = None

    @classmethod
    async def close_if_idle(cls) -> None:
        """Closes the browser only if nothing is using it *anywhere* — checked
        against the global _active_scrapes, not a per-caller local count. Both
        poll_prices (jobs.py) and #41's ad-hoc add-time batches (items.py) call
        this instead of close_browser() directly, since they run on the same
        event loop and can genuinely overlap: whichever caller's own batch
        finishes last is the one that actually closes it, while an earlier
        caller correctly sees non-zero (the other's scrapes still in flight)
        and skips closing.

        Shares _start_lock with start_browser() — without it, two callers
        finishing at nearly the same moment could both pass the
        _active_scrapes == 0 check and both call close_browser(), and since
        close_browser()'s own await on _context.close() leaves _context
        non-None until it returns, the second caller could call .close() on
        the same context a second time before the first caller ever nulls it
        out. Holding the lock across the whole check-and-close sequence
        (same pattern the old recycle_browser() used) makes the two callers'
        attempts serialize instead of overlapping."""
        async with cls._start_lock:
            if cls._active_scrapes == 0 and cls._context is not None:
                await cls.close_browser()

    async def get_price(self, url: str) -> ScraperResult:
        try:
            # Lazy launch — no-op once already running (see start_browser()'s own
            # fast-path check). Called on the base class explicitly, not via
            # self/cls, so a subclass invocation still shares the one browser.
            await PatchrightScraper.start_browser()
            PatchrightScraper._active_scrapes += 1
            try:
                page = await PatchrightScraper._context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_NAV_TIMEOUT_MS)
                    # Wait for Cloudflare challenge to clear (title changes from "Just a moment...")
                    try:
                        await page.wait_for_function("document.title !== 'Just a moment...'", timeout=CLOUDFLARE_CHALLENGE_TIMEOUT_MS)
                    except Exception:
                        pass
                    html = await page.content()
                finally:
                    await page.close()
            finally:
                PatchrightScraper._active_scrapes -= 1
            return await self._run_hierarchy(html, url)
        except Exception as exc:
            _log.warning("PatchrightScraper error for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error", error_reason=_describe_exception(exc))


# "/dp/<ASIN>" (also "/gp/product/<ASIN>", and the slugged "/Title/dp/<ASIN>")
# — matched on the path only, so tracking params never confuse it.
_AMAZON_ASIN_PATTERN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")


def _amazon_asin(url: str) -> str | None:
    match = _AMAZON_ASIN_PATTERN.search(url.split("?", 1)[0])
    return match.group(1) if match else None


def _as_soup(html: "str | BeautifulSoup") -> BeautifulSoup:
    """get_price parses the page once and hands the soup to every Amazon
    parser — on the Pi a 1-2 MB page is not free to parse three times."""
    return html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "html.parser")


def _amazon_has_no_new_offer(html: "str | BeautifulSoup") -> bool:
    """True when the page offers no new unit to buy — read from real
    amazon.ca markup, not guessed:
      - "used-only" box (#usedOnlyBuybox): the featured offer is a used /
        Warehouse one
      - "no featured offer" (#fod-cx-box + #unqualifiedBuyBox, "See All
        Buying Options"): offers exist, none qualifies for the buy box
      - classic #outOfStock block
    The new buy box's own add-to-cart button is the exact id
    "add-to-cart-button"; the used box's is "add-to-cart-button-ubb". Its
    presence overrides every marker above, so a stray hidden template can
    never turn a purchasable new item into "out of stock"."""
    soup = _as_soup(html)
    if soup.find(id="add-to-cart-button"):
        return False
    return any(soup.find(id=marker) for marker in ("usedOnlyBuybox", "unqualifiedBuyBox", "fod-cx-box", "outOfStock"))


# Containers that mean "the whole page" — a price found only at this level is
# not inside the buy box.
_PAGE_ROOTS = {"body", "html", "[document]"}
_CUSTOMER_VISIBLE_AMOUNT = re.compile(r"customerVisiblePrice\]\[amount\]$")


def _amazon_new_price(html: "str | BeautifulSoup") -> float | None:
    """The price of the NEW buy box, or None when it can't be read from inside
    that box (the caller reports an error — never a guessed price).

    Anchored on the exact-id #add-to-cart-button: the used box's button is
    "add-to-cart-button-ubb", so a used or no-offer page never has a new price
    to read. From the button, walk up to the nearest container that holds a
    price-to-pay node (.apex-pricetopay-value) and read its first non-empty
    .a-offscreen — in the accordion layout that container is the new row (the
    used row is its sibling, so it can't be reached); in the plain layout it is
    the buy-box section. Verified against real amazon.ca markup (2026-10-12).

    Deliberately not used: [data-pricetopay-label] (reflects the featured offer,
    which can be used, and its text can read "$X with N percent savings") and
    any page-wide scan (picks up delivery fees, import-fee breakdowns, "Other
    sellers" prices). If the node is empty, the customerVisiblePrice amount in
    the button's own form is the fallback."""
    soup = _as_soup(html)
    button = soup.find(id="add-to-cart-button")
    if button is None:
        return None

    scope = button.parent
    while scope is not None and scope.name not in _PAGE_ROOTS and scope.select_one(".apex-pricetopay-value") is None:
        scope = scope.parent
    if scope is not None and scope.name not in _PAGE_ROOTS:
        for node in scope.select(".apex-pricetopay-value .a-offscreen"):
            price = _parse_price(node.get_text(strip=True))
            if price is not None:
                return price

    form = button.find_parent("form")
    amount = form.find("input", attrs={"name": _CUSTOMER_VISIBLE_AMOUNT}) if form is not None else None
    return _parse_price(amount.get("value", "")) if amount is not None else None


def _amazon_used_price(html: "str | BeautifulSoup") -> float | None:
    """The used price shown by the used-only buy box (#usedBuySection), or None.
    Only meaningful when the page has no new offer — the caller checks that."""
    soup = _as_soup(html)
    for node in soup.select("#usedBuySection .offer-price"):
        price = _parse_price(node.get_text(strip=True))
        if price is not None:
            return price
    return None


class AmazonCAScraper(PatchrightScraper):
    MAX_RETRIES = AMAZON_MAX_RETRIES

    async def _find_product_title(self, page) -> str | None:
        """Feeds Product.name (issue #44) — AmazonCAScraper bypasses
        BaseScraper._run_hierarchy entirely (own price parsers, never the
        shared extraction pass), so it needs its own title read.
        #productTitle is Amazon's own stable element id for this. Non-fatal on failure — a
        missing/unreadable title just means product_title stays None,
        exactly like every other extraction path in this feature."""
        try:
            text = (await page.locator("#productTitle").first.text_content(timeout=PRICE_LOCATOR_TIMEOUT_MS) or "").strip()
            return text or None
        except Exception:
            return None

    async def get_price(self, url: str) -> ScraperResult:
        try:
            # Same lazy-launch call as the base class — explicit PatchrightScraper
            # reference so this subclass shares the one browser, not a second one.
            await PatchrightScraper.start_browser()
        except Exception as exc:
            _log.warning("AmazonCAScraper: browser launch failed for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error", error_reason=_describe_exception(exc))
        # Counts as one in-flight scrape for the whole retry loop below, not once
        # per attempt — matches PatchrightScraper.get_price()'s tracking, which
        # close_if_idle() checks before closing the shared context.
        PatchrightScraper._active_scrapes += 1
        # What the last failed attempt saw — a new buy box whose price can't be
        # read is a layout problem worth naming, not just "exhausted retries".
        failure_reason = "exhausted retries"
        try:
            for _ in range(self.MAX_RETRIES):
                try:
                    page = await PatchrightScraper._context.new_page()
                    try:
                        await page.goto("https://www.amazon.ca", wait_until="domcontentloaded", timeout=PAGE_NAV_TIMEOUT_MS)
                        await page.goto(url, wait_until="load", timeout=PAGE_NAV_TIMEOUT_MS)
                        # A sold-out variant redirects to a *different* ASIN
                        # (another color) whose price is not this item's —
                        # never read it, new or used. Skipped when either URL
                        # has no recognizable ASIN (short links, captcha pages).
                        tracked_asin, served_asin = _amazon_asin(url), _amazon_asin(page.url)
                        variant_gone = bool(tracked_asin and served_asin and tracked_asin != served_asin)
                        if variant_gone:
                            _log.info("AmazonCAScraper: %s redirected to a different ASIN (%s -> %s)", url, tracked_asin, served_asin)
                        # One snapshot, one parse per attempt (issue #60): every
                        # price below is read from this soup, scoped to the new
                        # (or used-only) buy box — never from the whole page.
                        soup = _as_soup(await page.content())
                        no_new_offer = not variant_gone and _amazon_has_no_new_offer(soup)
                        price = used_price = title = None
                        if not variant_gone and not no_new_offer:
                            price = _amazon_new_price(soup)
                            if price is None and soup.find(id="add-to-cart-button"):
                                failure_reason = "price not found in the new buy box"
                            # Only fetched on the attempt that's actually going
                            # to succeed — an extra Playwright DOM round-trip on
                            # every failed retry (page didn't load right, price
                            # element missing, etc.) would be wasted anyway,
                            # since that attempt's whole result gets discarded
                            # (review finding).
                            title = await self._find_product_title(page) if price is not None else None
                        elif no_new_offer:
                            used_price = _amazon_used_price(soup)
                        is_oos = variant_gone or no_new_offer
                    finally:
                        await page.close()
                    if price is not None:
                        # Issue #45 — amazon.ca is a fixed single site, and
                        # this scraper never calls _run_hierarchy /
                        # _extract_currency (own price parsers, never the
                        # shared extraction pass), so it needs its own
                        # hardcoded currency same as its own title read above.
                        return ScraperResult(price=price, status="ok", product_title=title, currency="CAD")
                    if is_oos:
                        return ScraperResult(price=None, status="oos", currency="CAD", used_price=used_price)
                except Exception:
                    _log.debug("AmazonCAScraper attempt failed for %s", url, exc_info=True)
            _log.warning("AmazonCAScraper gave up on %s: %s", url, failure_reason)
            return ScraperResult(price=None, status="error", error_reason=failure_reason)
        finally:
            PatchrightScraper._active_scrapes -= 1
