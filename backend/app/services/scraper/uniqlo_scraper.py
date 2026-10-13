import asyncio
import logging
import random
import re
from urllib.parse import parse_qs, urlparse

import httpx

from app.services.scraper.base import USER_AGENTS, BaseScraper, _build_headers, _describe_exception
from app.services.scraper.config import HTTP_TIMEOUT_SECONDS, UNIQLO_CLIENT_IDS
from app.services.scraper.result import ScraperResult

_log = logging.getLogger(__name__)

_VALID_CURRENCIES = {"USD", "CAD", "KRW"}

# "/ca/en/products/E491096-000/00" — region, language, product ID, then an
# optional price group. Matched against the URL's path only, so tracking
# params in the query string can never confuse it.
_PRODUCT_PATH = re.compile(
    r"^/(?P<region>[a-z]{2})/(?P<lang>[a-z]{2})/products/(?P<product_id>[A-Z]\d{5,7}-\d{3})(?:/(?P<price_group>\d{2}))?"
)

_API_URL = "https://www.uniqlo.com/{region}/api/commerce/v5/{lang}/products/{product_id}/price-groups/{price_group}/l2s"
# Small product lookup (~4 KB) that carries the item name plus the color and
# size names — the l2s call above has only codes, no names.
_LOOKUP_URL = "https://www.uniqlo.com/{region}/api/commerce/v5/{lang}/products"


class UniqloScraper(BaseScraper):
    """No browser needed — Uniqlo's product page is a client-rendered SPA with
    no JSON-LD/og:price/__NEXT_DATA__ for the generic hierarchy to read, but
    its own storefront loads price and per-variant stock from one commerce
    API call, which is replicated here (issue #58). That API is internal and
    undocumented: every failure returns status="error" with a specific reason
    (the API's own message, HTTP status, variant not found), never a guessed
    price. Registered in RETAILER_MAP (router.py), so there is no fallback,
    same as IKEAScraper and AmazonCAScraper. Canada only — see
    UNIQLO_CLIENT_IDS."""

    async def get_price(self, url: str) -> ScraperResult:
        parsed = urlparse(url)
        match = _PRODUCT_PATH.match(parsed.path)
        if match is None:
            _log.warning("UniqloScraper: no product ID found in %s", url)
            return _error("no Uniqlo product ID found in URL")

        region = match.group("region")
        client_id = UNIQLO_CLIENT_IDS.get(region)
        if client_id is None:
            return _error(f"unsupported Uniqlo region '{region}'")

        qs = parse_qs(parsed.query)
        color = (qs.get("colorDisplayCode") or [None])[0]
        size = (qs.get("sizeDisplayCode") or [None])[0]
        product_id = match.group("product_id")

        api_url = _API_URL.format(
            region=region,
            lang=match.group("lang"),
            product_id=product_id,
            price_group=match.group("price_group") or "00",
        )
        headers = {
            **_build_headers(random.choice(USER_AGENTS)),
            "Accept": "application/json",
            "x-fr-clientid": client_id,
        }
        params = {"withPrices": "true", "withStocks": "true", "includePreviousPrice": "false", "httpFailure": "true"}

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS) as client:
                # The name lookup runs alongside the stock call and can never
                # fail the scrape: _fetch_title swallows its own errors.
                resp, title = await asyncio.gather(
                    client.get(api_url, headers=headers, params=params),
                    _fetch_title(client, match.group("region"), match.group("lang"), product_id, headers, color, size),
                )

            # Issue #64 — from here on every error carries `title`: the name
            # lookup is a separate catalog call keyed by product ID, so a
            # resolved name means a real product whatever the stock call did.
            body = _json_or_none(resp)
            if resp.status_code != 200 or not isinstance(body, dict) or body.get("status") != "ok":
                return _error(f"Uniqlo API HTTP {resp.status_code}: {_api_message(body)}", title)

            result = body.get("result") or {}
            l2s, stocks, prices = result.get("l2s"), result.get("stocks"), result.get("prices")
            if not isinstance(l2s, list) or not isinstance(stocks, dict) or not isinstance(prices, dict):
                return _error("unexpected Uniqlo API response shape", title)

            candidates = [
                l2
                for l2 in l2s
                if (color is None or l2["color"]["displayCode"] == color)
                and (size is None or l2["size"]["displayCode"] == size)
            ]
            if not candidates:
                wanted = ", ".join(f"{name}={value}" for name, value in (("color", color), ("size", size)) if value)
                return _error(f"variant {wanted or 'any'} not found for {product_id}", title)

            # Both given: exactly that variant, in stock or not. Otherwise the
            # URL names the product (or one color of it), not one size: sold
            # out only when every candidate is, else price the first one that
            # can be bought rather than whichever happens to be listed first.
            variant = next((l2 for l2 in candidates if _in_stock(stocks.get(l2["l2Id"]))), candidates[0])
            l2_id = variant["l2Id"]
            stock, price_entry = stocks.get(l2_id), prices.get(l2_id)
            if stock is None or price_entry is None:
                return _error(f"no stock or price data for variant {l2_id} of {product_id}", title)

            base = price_entry["base"]
            promo = price_entry.get("promo")
            price = float((promo or base)["value"])
            raw_currency = (base.get("currency") or {}).get("code")
            currency = raw_currency if raw_currency in _VALID_CURRENCIES else None

            # Price and stock are separate attributes here, like IKEA: a
            # sold-out variant still has a real, known price.
            status = "ok" if _in_stock(stock) else "oos"
            return ScraperResult(price=price, status=status, currency=currency, product_title=title)
        except Exception as exc:
            _log.warning("UniqloScraper error for %s", url, exc_info=True)
            return _error(_describe_exception(exc))


async def _fetch_title(
    client: httpx.AsyncClient,
    region: str,
    lang: str,
    product_id: str,
    headers: dict[str, str],
    color: str | None,
    size: str | None,
) -> str | None:
    """Item name for Product.name inference (#44), with the tracked variant's
    color and size names appended — "Zip Up Blouson (BLUE, M)" — so two
    variants of one product get distinguishable names. Returns None on any
    failure; a missing name must never turn a good price/stock scrape into
    an error."""
    try:
        resp = await client.get(
            _LOOKUP_URL.format(region=region, lang=lang),
            headers=headers,
            params={"productIds": product_id},
        )
        body = _json_or_none(resp)
        if resp.status_code != 200 or not isinstance(body, dict) or body.get("status") != "ok":
            return None
        items = (body.get("result") or {}).get("items") or []
        item = next((i for i in items if i.get("productId") == product_id), None)
        name = item.get("name") if item else None
        if not isinstance(name, str) or not name.strip():
            return None
        parts = [
            option["name"]
            for chosen, options in ((color, item.get("colors")), (size, item.get("sizes")))
            if chosen
            for option in (options or [])
            if option.get("displayCode") == chosen and option.get("name")
        ]
        return f"{name.strip()} ({', '.join(parts)})" if parts else name.strip()
    except Exception:
        _log.info("UniqloScraper: name lookup failed for %s", product_id, exc_info=True)
        return None


def _error(reason: str, title: str | None = None) -> ScraperResult:
    return ScraperResult(price=None, status="error", error_reason=reason, product_title=title)


def _in_stock(stock: dict | None) -> bool:
    if not isinstance(stock, dict):
        return False
    return (stock.get("quantity") or 0) > 0 and stock.get("statusCode") != "STOCK_OUT"


def _json_or_none(resp: httpx.Response):
    try:
        return resp.json()
    except ValueError:
        return None


def _api_message(body) -> str:
    """The API's own error text (e.g. "invalid or missing client id") so a
    rotated client ID is diagnosable from the UI tooltip."""
    if isinstance(body, dict):
        details = (body.get("error") or {}).get("details") or []
        if details and isinstance(details[0], dict) and details[0].get("message"):
            return str(details[0]["message"])
    return "no details"
