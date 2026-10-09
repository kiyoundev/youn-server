import json
import logging
import random
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import USER_AGENTS, BaseScraper, _build_headers, _describe_exception
from app.services.scraper.config import HTTP_TIMEOUT_SECONDS, IKEA_STORE_ID
from app.services.scraper.result import ScraperResult

_log = logging.getLogger(__name__)

_VALID_CURRENCIES = {"USD", "CAD", "KRW"}

# Matched against the URL's path only, never the raw URL — a query string
# (e.g. a Google Shopping "?srsltid=..." tracking param, seen elsewhere in
# this app's real pasted URLs) sitting after the item number would otherwise
# either break the trailing anchor or, worse, silently match a numeric
# tracking/session param instead of the real item number.
_ITEM_NO_PATTERN = re.compile(r"(\d{6,})/?$")


class IKEAScraper(BaseScraper):
    """No browser needed — the fragment endpoint below is a plain JSON-
    backed HTTP request, same request IKEA's own frontend makes after page
    load. Registered in RETAILER_MAP (router.py), so a failure here returns
    status="error" with no fallback, same as AmazonCAScraper."""

    async def get_price(self, url: str) -> ScraperResult:
        match = _ITEM_NO_PATTERN.search(urlparse(url).path)
        if match is None:
            _log.warning("IKEAScraper: no item number found in %s", url)
            return ScraperResult(price=None, status="error", error_reason="no item number found in URL")
        item_no = match.group(1)

        fragment_url = (
            "https://www.ikea.com/ca/en/lower-funnel-fragments/"
            f"product-availability/?itemNo={item_no}&inline"
        )
        try:
            ua = random.choice(USER_AGENTS)
            async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(fragment_url, headers=_build_headers(ua))
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            tag = soup.find("script", type="text/hydrate")
            if not tag or not tag.string:
                return ScraperResult(
                    price=None, status="error", error_reason="availability data missing from IKEA response"
                )
            data = json.loads(tag.string)
            # IKEA now wraps the payload as {"0": {"loaderData": {...}}}
            # (hydration-island format); older responses had it at the top
            # level. Accept both so a format flip doesn't break every item.
            if "product" not in data:
                data = data.get("0", {}).get("loaderData", data)

            product = data["product"]
            raw_currency = product.get("currencyCode")
            currency = raw_currency if raw_currency in _VALID_CURRENCIES else None
            stores = data["availabilityResponse"]["availability"]["stores"]
            store = stores.get(IKEA_STORE_ID)

            price = float(product["price"])

            if store and store.get("isOutOfStock"):
                # IKEA shows price and availability as separate attributes —
                # a sold-out item still has a real, known price. Keep it on
                # the "oos" result rather than nulling it out the way the
                # generic Shopify/JSON-LD OOS paths do (those genuinely have
                # no price signal at all once OOS; IKEA's fragment endpoint
                # always includes one regardless of stock).
                restocks = (store.get("restocks") or {}).get("shortDate")
                restock_at = "–".join(restocks) if restocks else None
                return ScraperResult(price=price, status="oos", currency=currency, restock_at=restock_at)

            return ScraperResult(price=price, status="ok", currency=currency)
        except Exception as exc:
            _log.warning("IKEAScraper error for %s", url, exc_info=True)
            return ScraperResult(price=None, status="error", error_reason=_describe_exception(exc))
