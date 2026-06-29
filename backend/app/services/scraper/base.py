import json
import random
import re
from abc import ABC, abstractmethod
from functools import reduce
from operator import getitem
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.config import NEXTDATA_PATHS
from app.services.scraper.result import ScraperResult

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
]


def _build_headers(ua: str) -> dict[str, str]:
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-CA,en;q=0.9",
    }


def _parse_price(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d.,]", "", raw)
    if not cleaned:
        return None

    dot_pos = cleaned.rfind(".")
    comma_pos = cleaned.rfind(",")

    if dot_pos >= 0 and comma_pos >= 0:
        # Both present — whichever comes last is the decimal separator
        if dot_pos > comma_pos:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif comma_pos >= 0:
        # Only commas — 2-digit tail = decimal; 3-digit groups = thousand
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[-1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    # Only dots: leave as-is, float() parses directly

    try:
        result = float(cleaned)
        return result if result > 0 else None
    except ValueError:
        return None


def _find_jsonld_product(data: Any) -> dict | None:
    if isinstance(data, list):
        for item in data:
            found = _find_jsonld_product(item)
            if found:
                return found
    elif isinstance(data, dict):
        types = data.get("@type", "")
        if isinstance(types, str):
            types = [types]
        if "Product" in types:
            return data
        if "@graph" in data:
            found = _find_jsonld_product(data["@graph"])
            if found:
                return found
    return None


def _price_from_offer(offers: Any) -> ScraperResult | None:
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None

    raw = offers.get("lowPrice") if offers.get("@type") == "AggregateOffer" else offers.get("price")
    if raw is None:
        return None

    price = _parse_price(str(raw))
    if price is None:
        return None

    availability = str(offers.get("availability", ""))
    if "OutOfStock" in availability:
        return ScraperResult(price=None, status="oos")

    return ScraperResult(price=price, status="ok")


def _search_price_recursive(data: Any) -> float | None:
    if isinstance(data, dict):
        if "price" in data:
            val = data["price"]
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
            if isinstance(val, str):
                parsed = _parse_price(val)
                if parsed and parsed > 0:
                    return parsed
        for v in data.values():
            result = _search_price_recursive(v)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _search_price_recursive(item)
            if result is not None:
                return result
    return None


class BaseScraper(ABC):
    @abstractmethod
    async def get_price(self, url: str) -> ScraperResult:
        ...

    async def _extract_shopify(self, html: str, url: str) -> ScraperResult | None:
        parsed = urlparse(url)
        if "/products/" not in parsed.path:
            return None

        handle = parsed.path.rstrip("/").split("/")[-1].removesuffix(".html")
        api_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.json"

        qs = parse_qs(parsed.query)
        variant_id = (qs.get("variant", [None]) or [None])[0]

        try:
            ua = random.choice(USER_AGENTS)
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                resp = await client.get(api_url, headers=_build_headers(ua))
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "product" not in data:
                return None

            variants = data["product"].get("variants", [])
            if not variants:
                return None

            if variant_id:
                variant = next((v for v in variants if str(v.get("id")) == variant_id), variants[0])
            else:
                variant = variants[0]

            if not variant.get("available", True):
                return ScraperResult(price=None, status="oos")

            price = _parse_price(str(variant.get("price", "")))
            if price is None:
                return None
            return ScraperResult(price=price, status="ok")
        except Exception:
            return None

    def _extract_jsonld(self, soup: BeautifulSoup) -> ScraperResult | None:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            product = _find_jsonld_product(data)
            if product and "offers" in product:
                result = _price_from_offer(product["offers"])
                if result is not None:
                    return result
        return None

    def _extract_og_price(self, soup: BeautifulSoup) -> ScraperResult | None:
        for prop in ("og:price:amount", "product:price:amount"):
            tag = soup.find("meta", property=prop)
            if tag and tag.get("content"):
                price = _parse_price(tag["content"])
                if price is not None:
                    return ScraperResult(price=price, status="ok")
        return None

    def _extract_nextdata(self, soup: BeautifulSoup, url: str) -> ScraperResult | None:
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return None

        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            return None

        hostname = urlparse(url).hostname or ""
        explicit_path = NEXTDATA_PATHS.get(hostname)

        if explicit_path:
            try:
                val = reduce(getitem, explicit_path, data)
                price = _parse_price(str(val)) if isinstance(val, str) else (float(val) if isinstance(val, (int, float)) and val > 0 else None)
                if price:
                    return ScraperResult(price=price, status="ok")
            except (KeyError, TypeError, IndexError):
                pass

        price = _search_price_recursive(data)
        if price:
            return ScraperResult(price=price, status="ok")
        return None

    async def _run_hierarchy(self, html: str, url: str) -> ScraperResult:
        result = await self._extract_shopify(html, url)
        if result is not None:
            return result
        soup = BeautifulSoup(html, "html.parser")
        result = self._extract_jsonld(soup)
        if result is not None:
            return result
        result = self._extract_og_price(soup)
        if result is not None:
            return result
        result = self._extract_nextdata(soup, url)
        if result is not None:
            return result
        return ScraperResult(price=None, status="error")
