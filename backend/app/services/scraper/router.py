from urllib.parse import urlparse

from app.services.scraper.base import BaseScraper
from app.services.scraper.http_scraper import HTTPScraper
from app.services.scraper.patchright_scraper import AmazonCAScraper, PatchrightScraper
from app.services.scraper.result import ScraperResult

RETAILER_MAP: dict[str, type[BaseScraper]] = {
    "amazon.ca": AmazonCAScraper,
}

# Friendly display names, checked first by _derive_retailer() — for hostnames
# a trailing-TLD strip (_strip_tld_suffix below) can't fix on its own: a
# two-level TLD (29cm.co.kr's ".co.kr") or, for 29CM/Musinsa, a scraped
# og:site_name that's a full Korean marketing tagline ("감도 깊은 취향
# 셀렉트샵 29CM") or Hangul brand name (무신사) rather than a short display
# name. amazon.ca needs no entry — "amazon.ca" -> "Amazon" falls out of the
# generic TLD strip below. Hostnames not registered here (or in RETAILER_MAP)
# keep the generic (TLD-stripped) form.
RETAILER_DISPLAY_NAMES: dict[str, str] = {
    "29cm.co.kr": "29CM",
    "musinsa.com": "Musinsa",
}

# Single-segment TLDs common enough across tracked retailers' storefronts
# that stripping them generically beats a RETAILER_DISPLAY_NAMES entry per
# country (amazon.ca, walmart.com, walmart.ca, ... would otherwise all need
# one). Deliberately short/generic — a two-level TLD (co.kr, co.uk) or an
# unlisted one falls through unchanged and relies on a curated
# RETAILER_DISPLAY_NAMES entry or its real og:site_name instead.
_GENERIC_TLDS = {"ca", "com", "net", "org"}


def _hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _strip_tld_suffix(name: str) -> str:
    """Drops a trailing generic TLD ("Amazon.ca" -> "Amazon", "walmart.com"
    -> "walmart"). Applied both to the hostname fallback below and to real
    scraped og:site_name metadata (see jobs.py) — some sites' site_name is
    literally the bare domain rather than a proper brand name. Left
    unchanged when there's no dot, or the tail isn't a recognized generic
    TLD, so this never mangles a name that just happens to contain a '.'."""
    head, sep, tail = name.rpartition(".")
    if sep and head and tail.lower() in _GENERIC_TLDS:
        return head
    return name


def _derive_retailer(hostname: str) -> str:
    if hostname in RETAILER_DISPLAY_NAMES:
        return RETAILER_DISPLAY_NAMES[hostname]
    return _strip_tld_suffix(hostname).replace(".", "_").capitalize()


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
