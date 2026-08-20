import dataclasses
import json
import random
import re
from abc import ABC, abstractmethod
from functools import reduce
from operator import getitem
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.config import HTTP_TIMEOUT_SECONDS, NEXTDATA_PATHS
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


def _find_jsonld_type(data: Any, target_types: set[str]) -> dict | None:
    if isinstance(data, list):
        for item in data:
            found = _find_jsonld_type(item, target_types)
            if found:
                return found
    elif isinstance(data, dict):
        types = data.get("@type", "")
        if isinstance(types, str):
            types = [types]
        if target_types.intersection(types):
            return data
        if "@graph" in data:
            found = _find_jsonld_type(data["@graph"], target_types)
            if found:
                return found
    return None


def _find_jsonld_product(data: Any) -> dict | None:
    return _find_jsonld_type(data, {"Product"})


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


# Issue #44 — <title> heuristic fallback for site_name/product_title, used
# only when og tags and JSON-LD both come up empty. Many sites format
# <title> as "Product – Site Name" or "Product | Site Name"; deliberately
# conservative — only one recognized separator *character* may appear
# (checking membership, not counting how many times each occurs), and it
# must split into exactly two non-empty halves, or this returns None rather
# than risk a wrong guess on an ambiguous title.
_TITLE_SEPARATORS = ("–", "—", "|", "-")


def _split_title(title: str) -> tuple[str, str] | None:
    title = title.strip()
    found = [sep for sep in _TITLE_SEPARATORS if sep in title]
    if len(found) != 1:
        return None
    parts = [p.strip() for p in title.split(found[0])]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _first_title_segment(title: str) -> str | None:
    split = _split_title(title)
    return split[0] if split else None


def _last_title_segment(title: str) -> str | None:
    split = _split_title(title)
    return split[1] if split else None


def _strip_trailing_site_name(product_title: str, site_name: str | None) -> str:
    """Cleans a product_title that carries its own trailing site-name
    suffix — common with og:title (e.g. "Product – Site Name"), since it's
    the page's <title>-adjacent tag, not a dedicated product-name field the
    way JSON-LD's Product.name is. Only strips when the tail actually
    matches the already-known site_name (case-insensitive) — not a blind
    split on every og:title, since a "-"/"|" can legitimately be part of a
    real product name (e.g. "Air Force 1 - Low"); stripping on a guess
    would risk truncating those. No-op (returns product_title unchanged)
    if site_name is unknown, or the split doesn't match it."""
    if not site_name:
        return product_title
    split = _split_title(product_title)
    if split and split[1].strip().lower() == site_name.strip().lower():
        return split[0]
    return product_title


def _parse_jsonld_scripts(soup: BeautifulSoup) -> list[Any]:
    """Parses every ld+json <script> tag on the page once. _extract_jsonld
    (price), _extract_site_name, and _extract_product_title all need to
    scan the same JSON-LD blocks for different @types — without this,
    _run_hierarchy calling all three would re-parse identical script tags
    up to 3 times per scrape. Callers that already have a parsed list (e.g.
    _run_hierarchy, which needs all three) pass it in; direct/standalone
    calls (e.g. tests calling one of these functions in isolation) get it
    computed on demand via each function's own default."""
    parsed = []
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            parsed.append(json.loads(script_tag.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return parsed


def _extract_site_name(soup: BeautifulSoup, jsonld_scripts: list[Any] | None = None) -> str | None:
    """Feeds Listing.retailer (issue #44). Priority: og:site_name meta ->
    JSON-LD Organization/Brand -> <title> tail-segment heuristic."""
    tag = soup.find("meta", property="og:site_name")
    if tag and tag.get("content"):
        return tag["content"].strip()
    scripts = jsonld_scripts if jsonld_scripts is not None else _parse_jsonld_scripts(soup)
    for data in scripts:
        org = _find_jsonld_type(data, {"Organization", "Brand"})
        name = org.get("name") if org else None
        # JSON-LD comes from the scraped page itself, untrusted content —
        # spec says `name` should be a string, but nothing enforces that;
        # malformed JSON-LD (e.g. name as a nested object) shouldn't turn
        # into a garbage str(...)-coerced display value.
        if isinstance(name, str) and name:
            return name.strip()
    if soup.title and soup.title.string:
        return _last_title_segment(soup.title.string)
    return None


def _extract_product_title(soup: BeautifulSoup, jsonld_scripts: list[Any] | None = None) -> str | None:
    """Feeds Product.name (issue #44). Priority: og:title meta -> JSON-LD
    Product.name -> <title> lead-segment heuristic."""
    tag = soup.find("meta", property="og:title")
    if tag and tag.get("content"):
        return tag["content"].strip()
    scripts = jsonld_scripts if jsonld_scripts is not None else _parse_jsonld_scripts(soup)
    for data in scripts:
        product = _find_jsonld_product(data)
        name = product.get("name") if product else None
        if isinstance(name, str) and name:
            return name.strip()
    if soup.title and soup.title.string:
        return _first_title_segment(soup.title.string)
    return None


# Issue #45 — currency detection. Priority: explicit metadata/symbol for
# USD/KRW -> .kr TLD for KRW -> CAD default. Deliberately *not* symmetric
# between USD and CAD: an earlier draft TLD-split bare "$" into CAD (.ca)
# vs USD (else), but the real motivating counterexample (muddygeorge.com,
# a Canadian retailer on a plain .com domain) proved TLD can't reliably
# separate USD from CAD, so CAD - the common case for this app's users -
# is just the flat default absent an explicit USD signal. KRW keeps a TLD
# tier because the real KRW site in this codebase (goyowear.kr) doesn't
# mark currency on-page at all (see its regression fixture in
# test_base.py) - metadata/symbol alone would silently mis-default it to
# CAD, off by ~1000x in magnitude terms.
_SUPPORTED_CURRENCIES = {"USD", "CAD", "KRW"}


def _extract_currency(
    soup: BeautifulSoup, url: str, jsonld_scripts: list[Any] | None = None
) -> Literal["USD", "CAD", "KRW"]:
    tag = soup.find("meta", property="og:price:currency") or soup.find(
        "meta", property="product:price:currency"
    )
    if tag and tag.get("content"):
        code = tag["content"].strip().upper()
        if code in _SUPPORTED_CURRENCIES:
            return code  # type: ignore[return-value]

    scripts = jsonld_scripts if jsonld_scripts is not None else _parse_jsonld_scripts(soup)
    for data in scripts:
        product = _find_jsonld_product(data)
        offers = product.get("offers") if product else None
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict):
            code = offers.get("priceCurrency")
            if isinstance(code, str) and code.strip().upper() in _SUPPORTED_CURRENCIES:
                return code.strip().upper()  # type: ignore[return-value]

    # Symbol/text scan across the full rendered page text — the price
    # extractors above only ever hand back a parsed float, not the raw
    # text it came from, so there's no single "price-adjacent" node to
    # anchor to; a page-wide scan is the practical alternative and these
    # markers are distinctive enough that a false positive elsewhere on
    # the page is very unlikely.
    text = soup.get_text(" ", strip=True)
    if "₩" in text or "원" in text:
        return "KRW"
    if "US$" in text or re.search(r"\bUSD\b", text):
        return "USD"

    hostname = urlparse(url).hostname or ""
    if hostname.endswith(".kr"):
        return "KRW"

    return "CAD"


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
            async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS) as client:
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

    def _extract_jsonld(self, soup: BeautifulSoup, jsonld_scripts: list[Any] | None = None) -> ScraperResult | None:
        scripts = jsonld_scripts if jsonld_scripts is not None else _parse_jsonld_scripts(soup)
        for data in scripts:
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
        # soup is parsed unconditionally now (issue #44) — even on the
        # Shopify success path, which doesn't need it for price but does
        # need it for the name-extraction pass below, run independently of
        # which of these 4 price methods ends up winning.
        soup = BeautifulSoup(html, "html.parser")
        # Parsed once, shared by _extract_jsonld (price) and both name
        # extractors below — otherwise each would independently re-parse
        # the same <script type="application/ld+json"> tags (review finding).
        jsonld_scripts = _parse_jsonld_scripts(soup)
        if result is None:
            result = self._extract_jsonld(soup, jsonld_scripts)
        if result is None:
            result = self._extract_og_price(soup)
        if result is None:
            result = self._extract_nextdata(soup, url)
        if result is None:
            result = ScraperResult(price=None, status="error")

        site_name = _extract_site_name(soup, jsonld_scripts)
        product_title = _extract_product_title(soup, jsonld_scripts)
        if product_title:
            product_title = _strip_trailing_site_name(product_title, site_name)
        # Unlike site_name/product_title, currency always resolves to a
        # concrete value (CAD default) — no "both None, skip the replace"
        # short-circuit possible here, dataclasses.replace always runs.
        currency = _extract_currency(soup, url, jsonld_scripts)
        return dataclasses.replace(
            result, site_name=site_name, product_title=product_title, currency=currency
        )
