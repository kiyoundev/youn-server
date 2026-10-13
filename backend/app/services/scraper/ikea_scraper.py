import json
import logging
import random
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.scraper.base import USER_AGENTS, BaseScraper, _build_headers, _describe_exception
from app.services.scraper.config import HTTP_TIMEOUT_SECONDS
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
        # Issue #64 — metadata is attached to every outcome from the moment
        # the product object has been parsed (a later error still read a real
        # product page); before that there is nothing to attach.
        title: str | None = None
        currency: str | None = None

        fragment_url = (
            "https://www.ikea.com/ca/en/lower-funnel-fragments/"
            f"product-availability/?itemNo={item_no}&inline&storeId={settings.ikea_store_id}"
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
            title = _product_title(product)
            availability = data["availabilityResponse"]["availability"]
            store = availability["stores"].get(settings.ikea_store_id)

            price = float(product["price"])

            if store is not None:
                out_of_stock = bool(store.get("isOutOfStock"))
            else:
                # Store missing even though storeId was sent — fall back to
                # IKEA's own top-level flags rather than assuming in stock.
                out_of_stock = bool(
                    availability.get("isSoldOut")
                    or (availability.get("homeDelivery") or {}).get("isOutOfStock")
                )

            if out_of_stock:
                # IKEA shows price and availability as separate attributes —
                # a sold-out item still has a real, known price. Keep it on
                # the "oos" result rather than nulling it out the way the
                # generic Shopify/JSON-LD OOS paths do (those genuinely have
                # no price signal at all once OOS; IKEA's fragment endpoint
                # always includes one regardless of stock).
                restocks = ((store or {}).get("restocks") or {}).get("shortDate")
                restock_at = "–".join(restocks) if restocks else None
                return ScraperResult(price=price, status="oos", currency=currency, product_title=title, restock_at=restock_at)

            return ScraperResult(price=price, status="ok", currency=currency, product_title=title)
        except Exception as exc:
            _log.warning("IKEAScraper error for %s", url, exc_info=True)
            return ScraperResult(
                price=None,
                status="error",
                error_reason=_describe_exception(exc),
                product_title=title,
                currency=currency,
            )


def _product_title(product: dict) -> str | None:
    """Feeds Product.name (issue #44/#64). IKEA's product object splits the
    display name into `name` ("ALPSTUGA") and `typeName` ("air quality
    sensor"); joined the way IKEA's own page heading shows them. Either alone
    is still a usable name; neither is None."""
    name = product.get("name")
    name = name.strip() if isinstance(name, str) else ""
    type_name = product.get("typeName")
    type_name = type_name.strip() if isinstance(type_name, str) else ""
    if name and type_name:
        return f"{name} {type_name[0].upper()}{type_name[1:]}"
    return name or type_name or None
