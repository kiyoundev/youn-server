from urllib.parse import urlparse

from app.services.scraper.base import BaseScraper
from app.services.scraper.http_scraper import HTTPScraper
from app.services.scraper.patchright_scraper import AmazonCAScraper, PatchrightScraper
from app.services.scraper.result import ScraperResult

RETAILER_MAP: dict[str, type[BaseScraper]] = {
    "amazon.ca": AmazonCAScraper,
}


class RetailerRouter:
    async def get_price(self, url: str, scraper_type: str | None = None) -> ScraperResult:
        hostname = (urlparse(url).hostname or "").removeprefix("www.")

        if hostname in RETAILER_MAP:
            return await RETAILER_MAP[hostname]().get_price(url)

        if scraper_type == "patchright":
            return await PatchrightScraper().get_price(url)

        result = await HTTPScraper().get_price(url)
        if result.status == "error":
            result = await PatchrightScraper().get_price(url)
        return result


async def detect_scraper_type(url: str) -> str | None:
    """Probe an unknown-domain URL to determine which scraper it needs.

    Called once at item creation (POST /api/items) for domains not in
    RETAILER_MAP and with no explicit scraper_type override — the result is
    then cached on Listing so later polls skip straight to the right method.
    """
    result = await HTTPScraper().get_price(url)
    if result.status != "error":
        return None
    result = await PatchrightScraper().get_price(url)
    if result.status != "error":
        return "patchright"
    raise ValueError("URL not scrapable by any method")
