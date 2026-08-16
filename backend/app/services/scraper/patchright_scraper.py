import asyncio
import logging
import os
import tempfile

from patchright.async_api import Browser, BrowserContext, Playwright, async_playwright

_log = logging.getLogger(__name__)

from app.services.scraper.base import BaseScraper, _parse_price
from app.services.scraper.config import (
    AMAZON_MAX_RETRIES,
    CLOUDFLARE_CHALLENGE_TIMEOUT_MS,
    PAGE_NAV_TIMEOUT_MS,
    PRICE_LOCATOR_TIMEOUT_MS,
)
from app.services.scraper.result import ScraperResult

_USER_DATA_DIR = os.path.join(tempfile.gettempdir(), "patchright-profile")


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
    # incremented/decremented around every get_price() call site. recycle_browser()
    # checks this to avoid closing the context out from under an in-flight scrape.
    _active_scrapes: int = 0

    @classmethod
    async def start_browser(cls) -> None:
        if cls._context is not None:
            return
        async with cls._start_lock:
            if cls._context is not None:  # re-check — another caller may have won the race
                return
            try:
                executable_path = os.environ.get("CHROMIUM_PATH")
                cls._playwright = await async_playwright().start()
                # Persistent context: cookies/localStorage survive across pages in a run,
                # making the session look like a returning user to bot detectors.
                cls._context = await cls._playwright.chromium.launch_persistent_context(
                    _USER_DATA_DIR,
                    headless=True,
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
    async def recycle_browser(cls) -> None:
        """Closes and relaunches the browser context, for long-uptime resilience
        (this app runs 24/7, so once launched the context otherwise never gets a
        fresh start). Shares _start_lock with start_browser() — serializes recycle
        against a concurrent launch, so a recycle tick landing mid-launch can't
        close a context that's still being constructed."""
        async with cls._start_lock:
            if cls._context is None:
                return  # never launched — nothing to recycle
            if cls._active_scrapes > 0:
                _log.info("recycle_browser: scrape in flight, skipping — retry next tick")
                return
            await cls.close_browser()
        await cls.start_browser()

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
                        await page.wait_for_function(
                            "document.title !== 'Just a moment...'", timeout=CLOUDFLARE_CHALLENGE_TIMEOUT_MS
                        )
                    except Exception:
                        pass
                    html = await page.content()
                finally:
                    await page.close()
            finally:
                PatchrightScraper._active_scrapes -= 1
            return await self._run_hierarchy(html, url)
        except Exception:
            _log.warning("PatchrightScraper error for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error")


class AmazonCAScraper(PatchrightScraper):
    MAX_RETRIES = AMAZON_MAX_RETRIES

    async def _find_price_text(self, page) -> str | None:
        # 1. Semantic: data-pricetopay-label is Amazon's own pricing attribute —
        #    stable across redesigns because Amazon's JS depends on it internally.
        try:
            if await page.locator("[data-pricetopay-label]").count():
                text = (
                    await page.locator("[data-pricetopay-label]").first.text_content(
                        timeout=PRICE_LOCATOR_TIMEOUT_MS
                    )
                    or ""
                ).strip()
                if text:
                    return text
        except Exception:
            pass

        # 2. Regex scan: any offscreen element whose text looks like a price.
        #    Works regardless of class or ID changes.
        return await page.evaluate(r"""
            () => {
                for (const el of document.querySelectorAll('.a-offscreen, .aok-offscreen')) {
                    const t = el.textContent.trim();
                    if (/^\$[\d,.]+$/.test(t)) return t;
                }
                return null;
            }
        """)

    async def get_price(self, url: str) -> ScraperResult:
        try:
            # Same lazy-launch call as the base class — explicit PatchrightScraper
            # reference so this subclass shares the one browser, not a second one.
            await PatchrightScraper.start_browser()
        except Exception:
            _log.warning("AmazonCAScraper: browser launch failed for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error")
        # Counts as one in-flight scrape for the whole retry loop below, not once
        # per attempt — matches PatchrightScraper.get_price()'s tracking, which
        # recycle_browser() checks before closing the shared context.
        PatchrightScraper._active_scrapes += 1
        try:
            for _ in range(self.MAX_RETRIES):
                try:
                    page = await PatchrightScraper._context.new_page()
                    try:
                        await page.goto(
                            "https://www.amazon.ca", wait_until="domcontentloaded", timeout=PAGE_NAV_TIMEOUT_MS
                        )
                        await page.goto(url, wait_until="load", timeout=PAGE_NAV_TIMEOUT_MS)
                        raw = await self._find_price_text(page)
                    finally:
                        await page.close()
                    price = _parse_price(raw or "")
                    if price is not None:
                        return ScraperResult(price=price, status="ok")
                except Exception:
                    _log.debug("AmazonCAScraper attempt failed for %s", url, exc_info=True)
            _log.warning("AmazonCAScraper exhausted retries for %s", url)
            return ScraperResult(price=None, status="error")
        finally:
            PatchrightScraper._active_scrapes -= 1
