import logging
import random

import httpx

from app.services.scraper.base import BaseScraper, USER_AGENTS, _build_headers
from app.services.scraper.config import HTTP_TIMEOUT_SECONDS
from app.services.scraper.result import ScraperResult

_log = logging.getLogger(__name__)


class HTTPScraper(BaseScraper):
    async def get_price(self, url: str) -> ScraperResult:
        try:
            ua = random.choice(USER_AGENTS)
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS, http2=True
            ) as client:
                resp = await client.get(url, headers=_build_headers(ua))
            return await self._run_hierarchy(resp.text, url)
        except Exception:
            _log.warning("HTTPScraper error for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error")
