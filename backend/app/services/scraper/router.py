from urllib.parse import urlparse

from app.services.scraper.base import BaseScraper
from app.services.scraper.http_scraper import HTTPScraper
from app.services.scraper.patchright_scraper import AmazonCAScraper, PatchrightScraper
from app.services.scraper.result import ScraperResult

RETAILER_MAP: dict[str, type[BaseScraper]] = {
    "amazon.ca": AmazonCAScraper,
}

# Friendly display names, checked first by _derive_retailer() so these don't
# fall through to the generic hostname.replace(".", "_") derivation
# ("amazon.ca" -> "amazon_ca"). Not limited to hostnames with dedicated
# scraper support (RETAILER_MAP above) — 29cm.co.kr/musinsa.com use the
# generic HTTPScraper/PatchrightScraper path but still get a short override
# here because their scraped og:site_name (see _extract_site_name) is a
# full Korean marketing tagline ("감도 깊은 취향 셀렉트샵 29CM") or, for
# Musinsa, its Hangul brand name (무신사) rather than a short display name.
# Hostnames not registered here (or in RETAILER_MAP) keep the generic form.
RETAILER_DISPLAY_NAMES: dict[str, str] = {
    "amazon.ca": "Amazon",
    "29cm.co.kr": "29CM",
    "musinsa.com": "Musinsa",
}


def _hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _derive_retailer(hostname: str) -> str:
    return RETAILER_DISPLAY_NAMES.get(hostname, hostname.replace(".", "_"))


class RetailerRouter:
    async def get_price(self, url: str, scraper_type: str | None = None) -> ScraperResult:
        hostname = _hostname_of(url)

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
