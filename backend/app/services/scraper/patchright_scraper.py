import logging
import os
import tempfile

from patchright.async_api import Browser, BrowserContext, Playwright, async_playwright

_log = logging.getLogger(__name__)

from app.services.scraper.base import BaseScraper, _parse_price
from app.services.scraper.result import ScraperResult

_USER_DATA_DIR = os.path.join(tempfile.gettempdir(), "patchright-profile")


class PatchrightScraper(BaseScraper):
    _playwright: Playwright | None = None
    _browser: Browser | None = None
    _context: BrowserContext | None = None

    @classmethod
    async def start_browser(cls) -> None:
        if cls._context is not None:
            return
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

    @classmethod
    async def close_browser(cls) -> None:
        if cls._context:
            await cls._context.close()
        if cls._playwright:
            await cls._playwright.stop()
        cls._browser = None
        cls._context = None
        cls._playwright = None

    async def get_price(self, url: str) -> ScraperResult:
        if PatchrightScraper._context is None:
            return ScraperResult(price=None, status="error")
        try:
            page = await PatchrightScraper._context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Wait for Cloudflare challenge to clear (title changes from "Just a moment...")
                try:
                    await page.wait_for_function(
                        "document.title !== 'Just a moment...'", timeout=20000
                    )
                except Exception:
                    pass
                html = await page.content()
            finally:
                await page.close()
            return await self._run_hierarchy(html, url)
        except Exception:
            _log.warning("PatchrightScraper error for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error")


class AmazonCAScraper(PatchrightScraper):
    MAX_RETRIES = 2

    async def _find_price_text(self, page) -> str | None:
        # 1. Semantic: data-pricetopay-label is Amazon's own pricing attribute —
        #    stable across redesigns because Amazon's JS depends on it internally.
        try:
            if await page.locator("[data-pricetopay-label]").count():
                text = (await page.locator("[data-pricetopay-label]").first.text_content(timeout=3000) or "").strip()
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
        if PatchrightScraper._context is None:
            return ScraperResult(price=None, status="error")
        for _ in range(self.MAX_RETRIES):
            try:
                page = await PatchrightScraper._context.new_page()
                try:
                    await page.goto("https://www.amazon.ca", wait_until="domcontentloaded", timeout=30000)
                    await page.goto(url, wait_until="load", timeout=30000)
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
