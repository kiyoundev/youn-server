import dataclasses
import json
import logging
import random
import re
from abc import ABC, abstractmethod
from functools import reduce
from operator import getitem
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup, CData, NavigableString

from app.services.scraper.config import HTTP_TIMEOUT_SECONDS, NEXTDATA_PATHS
from app.services.scraper.result import ScraperResult

_log = logging.getLogger(__name__)

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


def _describe_exception(exc: BaseException, max_len: int = 200) -> str:
    """Short, never-empty description of `exc` for ScraperResult.error_reason
    (issue #53) — raw str(exc) isn't safe to persist: it can be empty
    (httpx.ConnectError(""), a bare TimeoutError()) or a multi-line
    Playwright call log. First line only, type name alone when the message
    is empty, truncated so a tooltip stays readable."""
    lines = str(exc).strip().splitlines()
    message = lines[0].strip() if lines else ""
    text = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _detect_bot_block(soup: BeautifulSoup) -> str | None:
    """Content-based check for a bot-check/deny page (issue #53), run only
    once every extraction method has already come up empty. Deliberately by
    page content rather than a flag threaded from a specific scraper: the
    real case that motivated this (#52) was Akamai's hard "Access Denied",
    not the Cloudflare "Just a moment..." interstitial patchright_scraper.py
    already waits on — a Cloudflare-specific flag would have missed it.
    Only two known signatures; any other vendor's block page falls through
    to the caller's generic reason, so this is not an exhaustive detector."""
    title = soup.title.string.strip().lower() if soup.title and soup.title.string else ""
    if "just a moment" in title:
        return "Cloudflare bot-check challenge did not clear"
    if "access denied" in title:
        text = soup.get_text(" ", strip=True).lower()
        if "edgesuite" in text or "reference #" in text:
            return "Akamai bot-block (access denied)"
    return None


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


# schema.org ItemAvailability values meaning "can't buy it": SoldOut and
# Discontinued don't contain the text "OutOfStock", so match each by name.
_JSONLD_OOS_AVAILABILITY = ("OutOfStock", "SoldOut", "Discontinued")


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
    if any(value in availability for value in _JSONLD_OOS_AVAILABILITY):
        # Issue #68 — the page still lists a price; keep it (information
        # only: the scheduler never alerts on or charts an "oos" price).
        return ScraperResult(price=price, status="oos")

    return ScraperResult(price=price, status="ok")


# Wording varies by site ("out of stock", "outofstock", "oos", ...), so
# compare on a lowercased value with spaces/underscores/hyphens stripped.
_OG_OOS_VALUES = ("outofstock", "oos", "soldout", "discontinued")


def _og_out_of_stock(soup: BeautifulSoup) -> bool:
    for prop in ("og:availability", "product:availability"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            value = re.sub(r"[\s_\-]+", "", str(tag["content"]).lower())
            return any(marker in value for marker in _OG_OOS_VALUES)
    return False


def _search_price_recursive(data: Any, key: str = "price") -> float | None:
    if isinstance(data, dict):
        if key in data:
            val = data[key]
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
            if isinstance(val, str):
                parsed = _parse_price(val)
                if parsed and parsed > 0:
                    return parsed
        for v in data.values():
            result = _search_price_recursive(v, key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _search_price_recursive(item, key)
            if result is not None:
                return result
    return None


# NEXT_DATA/RSC-flight fallback tier list, checked in this order —
# storefronts commonly ship several price fields on the same product object
# (list price down to actually-payable price: site-wide sale, then a
# further stackable coupon on top). Plain "price" stays last so today's
# behavior is unchanged for pages that only have that one field. Global by
# design, not scoped to any one host — real shape observed on musinsa's
# __NEXT_DATA__ (goodsPrice: {salePrice, normalPrice, couponPrice,
# finalPrice, ...}) and 29CM's RSC/Flight stream (totalDiscountedItemPrice,
# issue #50), see test_base.py's regression fixtures for both.
_PRICE_KEY_PRIORITY = ("finalPrice", "couponPrice", "totalDiscountedItemPrice", "salePrice", "normalPrice", "price")


def _search_price_by_priority(data: Any) -> float | None:
    for key in _PRICE_KEY_PRIORITY:
        result = _search_price_recursive(data, key)
        if result is not None:
            return result
    return None


# Common product-ID field names across storefronts' NEXT_DATA — used to
# scope a priority-price search to the actual tracked product's node rather
# than the whole page tree, which also holds "related items" / "other
# colors" carousels carrying the *same* price field names for *different*
# products (see musinsa regression fixture: a dark-grey/blue/black jacket
# variant carousel, each with its own finalPrice). Without scoping,
# _search_price_by_priority's first-match-wins DFS is at the mercy of
# whatever key order the page happened to serialize in — right today by
# luck, not by construction. Global, no per-host config: any host whose
# NEXT_DATA uses one of these names and whose URL ends in a bare numeric ID
# gets scoping for free; anything else silently falls back to the unscoped
# whole-tree search (today's behavior), never an error. "itemNo" added for
# 29CM's RSC-flight rows (issue #50) — same reasoning, different site.
_ID_KEY_CANDIDATES = ("goodsNo", "productId", "productID", "itemId", "itemNo", "id", "sku", "pid")


def _extract_id_from_url(url: str) -> str | None:
    """Last purely-numeric path segment, e.g. "/products/5622799" ->
    "5622799". Generic across hosts on purpose — no per-site path config.
    None for URLs that don't end in a bare numeric segment; callers treat
    that as "can't scope, fall back to whole-tree search"."""
    path = urlparse(url).path
    for segment in reversed([s for s in path.split("/") if s]):
        if segment.isdigit():
            return segment
    return None


def _find_node_by_id(data: Any, id_value: str) -> dict | None:
    """DFS for the dict representing one specific product — matched by any
    of _ID_KEY_CANDIDATES holding a value equal (string-compared, since
    JSON may store the ID as either an int or a string) to id_value. Returns
    that dict itself, so a price search can be scoped to run inside it, or
    None if no node anywhere in the tree carries a matching ID. First-match
    DFS order no longer matters for correctness here the way it does for
    price keys: any node matching the real product's own ID reflects that
    same product's current price, regardless of which matching node (main
    data blob vs. a "recently viewed"/self-referencing carousel card) is
    found first."""
    if isinstance(data, dict):
        for id_key in _ID_KEY_CANDIDATES:
            if id_key in data and str(data[id_key]) == id_value:
                return data
        for v in data.values():
            found = _find_node_by_id(v, id_value)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_node_by_id(item, id_value)
            if found is not None:
                return found
    return None


# Issue #50 — Next.js App Router pages (29CM) don't emit a single
# __NEXT_DATA__ blob at all; their data ships as a stream of React Server
# Components ("Flight") chunks instead: <script>self.__next_f.push([id,
# "..."])</script>, one call per chunk, a real product page streaming on
# the order of 90+ of them. Two facts about this format drive the shape
# below (verified against 29CM's real page, see test_base.py's fixture):
#   1. A single logical "row" can be split across multiple push() calls —
#      the decoded string payloads have to be concatenated in document
#      order *before* splitting into rows, not parsed chunk-by-chunk.
#   2. Each row is "{hex-id}:{JSON payload}" and rows can *reference* each
#      other by id ("$a7") instead of nesting inline — unlike NEXT_DATA's
#      one nested tree, so a plain recursive search over one row alone can
#      miss a price that's one reference-hop away (see _resolve_rsc_refs).
# Best-effort throughout, matching this file's existing heuristic style —
# a row using Flight's own non-JSON wire syntax (import markers, hints,
# etc.) is silently skipped, not raised.
_RSC_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)")
_RSC_ROW_RE = re.compile(r"^([0-9a-f]+):(.*)$", re.S)


def _parse_rsc_flight_rows(html: str) -> dict[str, Any]:
    """Decodes every self.__next_f.push([...]) call in html into
    {row_id: parsed_value}. Returns {} if the page has no RSC/Flight
    chunks at all (e.g. it's a __NEXT_DATA__ or plain-HTML page) — callers
    treat that the same as "nothing found", not an error."""
    chunks: list[str] = []
    for match in _RSC_PUSH_RE.finditer(html):
        try:
            chunk = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if len(chunk) >= 2 and isinstance(chunk[1], str):
            chunks.append(chunk[1])
    if not chunks:
        return {}

    full_text = "".join(chunks)
    rows: dict[str, Any] = {}
    for raw_row in re.split(r"\n(?=[0-9a-f]+:)", full_text):
        match = _RSC_ROW_RE.match(raw_row)
        if not match:
            continue
        try:
            rows[match.group(1)] = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
    return rows


_RSC_REF_RE = re.compile(r"^\$([0-9a-f]+)$")


def _resolve_rsc_refs(value: Any, rows: dict[str, Any], depth: int = 2) -> Any:
    """Best-effort substitution of Flight reference strings ("$<row_id>")
    with that row's own already-parsed value — e.g. 29CM's product row has
    `internalDisplayPrice: "$a7"`, and row "a7" is where
    totalDiscountedItemPrice actually lives. `rows` is already fully
    parsed in memory, so resolving is just dict lookups, not new parsing
    or network work — cheap even across a node's many fields. Depth is
    bounded (not a full graph walk) so a reference cycle can't loop
    forever and an unrelated deeply-nested reference chain doesn't get
    chased further than needed to reach a price."""
    if depth <= 0:
        return value
    if isinstance(value, str):
        match = _RSC_REF_RE.match(value)
        if match and match.group(1) in rows:
            return _resolve_rsc_refs(rows[match.group(1)], rows, depth - 1)
        return value
    if isinstance(value, dict):
        return {k: _resolve_rsc_refs(v, rows, depth) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_rsc_refs(v, rows, depth) for v in value]
    return value


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


# Issue #45 — currency detection. Priority: a Shopify storefront's own
# declared currency (#63, below) -> explicit metadata/symbol for
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

# Issue #63 — a Shopify storefront states the currency it is actually
# presenting to the shopper in its own page scripts, e.g.
# `Shopify.currency = {"active":"CAD","rate":"1.44"}`. That is more reliable
# than a theme's JSON-LD, which can carry the shop's base currency instead:
# dickies.com/en-ca prices in CAD, but its Product JSON-LD says USD.
_SHOPIFY_CURRENCY_PATTERNS = (
    re.compile(r"""Shopify\.currency\s*=\s*\{[^}]*["']active["']\s*:\s*["']([A-Za-z]{3})["']"""),
    re.compile(r"""ShopifyAnalytics\.meta\.currency\s*=\s*["']([A-Za-z]{3})["']"""),
)


def _shopify_currency(soup: BeautifulSoup) -> Literal["USD", "CAD", "KRW"] | None:
    """The storefront currency a Shopify page declares, if it is one we
    support; None for non-Shopify pages or an unsupported currency (the
    caller then falls through to the other signals)."""
    for script in soup.find_all("script"):
        text = script.get_text()
        if "Shopify" not in text:
            continue
        for pattern in _SHOPIFY_CURRENCY_PATTERNS:
            match = pattern.search(text)
            if match and match.group(1).upper() in _SUPPORTED_CURRENCIES:
                return match.group(1).upper()  # type: ignore[return-value]
    return None


# Page chrome that routinely mentions other currencies without saying what
# the product costs: currency/region pickers (<select>/<option>), footers
# ("US orders ship from..."), and nav menus. Skipped by the text scan below.
_CURRENCY_SCAN_SKIP_TAGS = ("select", "option", "footer", "nav")


def _currency_scan_text(soup: BeautifulSoup) -> str:
    """Visible page text for the symbol/text scan, minus the chrome above.
    Same string types soup.get_text() uses (script/style/comment text is
    excluded), filtered per string instead of via a mutated copy of the
    tree."""
    parts = [
        string
        for string in soup.find_all(string=True)
        if type(string) in (NavigableString, CData)
        and not string.find_parent(_CURRENCY_SCAN_SKIP_TAGS)
    ]
    return " ".join(part.strip() for part in parts if part.strip())


def _detect_currency(
    soup: BeautifulSoup, url: str, jsonld_scripts: list[Any] | None = None
) -> tuple[Literal["USD", "CAD", "KRW"], str]:
    """(currency, signal that decided it). The signal name is logged by
    _run_hierarchy so a wrong currency can be traced to its cause."""
    shopify = _shopify_currency(soup)
    if shopify:
        return shopify, "shopify"

    tag = soup.find("meta", property="og:price:currency") or soup.find(
        "meta", property="product:price:currency"
    )
    if tag and tag.get("content"):
        code = tag["content"].strip().upper()
        if code in _SUPPORTED_CURRENCIES:
            return code, "meta"  # type: ignore[return-value]

    scripts = jsonld_scripts if jsonld_scripts is not None else _parse_jsonld_scripts(soup)
    for data in scripts:
        product = _find_jsonld_product(data)
        offers = product.get("offers") if product else None
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict):
            code = offers.get("priceCurrency")
            if isinstance(code, str) and code.strip().upper() in _SUPPORTED_CURRENCIES:
                return code.strip().upper(), "jsonld"  # type: ignore[return-value]

    # Symbol/text scan across the rendered page text — the price
    # extractors above only ever hand back a parsed float, not the raw
    # text it came from, so there's no single "price-adjacent" node to
    # anchor to; a page-wide scan is the practical alternative. Currency
    # pickers, footers and navs are left out (_currency_scan_text) since
    # they list or mention other currencies on any storefront.
    text = _currency_scan_text(soup)
    if "₩" in text or "원" in text:
        return "KRW", "text_scan"
    if "US$" in text or re.search(r"\bUSD\b", text):
        return "USD", "text_scan"

    hostname = urlparse(url).hostname or ""
    if hostname.endswith(".kr"):
        return "KRW", "tld"

    return "CAD", "default"


def _extract_currency(
    soup: BeautifulSoup, url: str, jsonld_scripts: list[Any] | None = None
) -> Literal["USD", "CAD", "KRW"]:
    return _detect_currency(soup, url, jsonld_scripts)[0]


class BaseScraper(ABC):
    @abstractmethod
    async def get_price(self, url: str) -> ScraperResult:
        ...

    async def _extract_shopify(self, html: str, url: str) -> ScraperResult | None:
        parsed = urlparse(url)
        if "/products/" not in parsed.path:
            return None

        # Keep whatever precedes "/products/" (a Shopify Markets locale
        # prefix like "/en-ca") — the bare "/products/{handle}" path
        # resolves to the store's default market, so dickies.com/en-ca/...
        # came back priced in USD while the CA page labels it CAD.
        prefix, _, tail = parsed.path.partition("/products/")
        handle = tail.rstrip("/").split("/")[0].removesuffix(".html")
        base_url = f"{parsed.scheme}://{parsed.netloc}{prefix}/products/{handle}"

        qs = parse_qs(parsed.query)
        variant_id = (qs.get("variant", [None]) or [None])[0]

        # .js is Shopify's documented Ajax Product API and carries per-variant
        # `available`; .json is undocumented and generally omits it, so a
        # sold-out variant read as in stock. .json stays as the fallback for
        # stores where .js fails.
        async with httpx.AsyncClient(follow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS) as client:
            result = await self._shopify_fetch(client, f"{base_url}.js", variant_id, cents=True)
            if result is not None:
                return result
            _log.info("Shopify .js gave no result for %s, trying .json", url)
            return await self._shopify_fetch(client, f"{base_url}.json", variant_id, cents=False)

    async def _shopify_fetch(
        self, client: httpx.AsyncClient, api_url: str, variant_id: str | None, *, cents: bool
    ) -> ScraperResult | None:
        """One Shopify product endpoint -> ScraperResult, or None on any
        failure so the caller can try the next endpoint. `cents`: the .js
        endpoint returns prices as integer cents, .json as decimal strings."""
        try:
            resp = await client.get(api_url, headers=_build_headers(random.choice(USER_AGENTS)))
            if resp.status_code != 200:
                return None
            data = resp.json()
            product = data if cents else data.get("product")
            if not isinstance(product, dict):
                return None

            variants = product.get("variants", [])
            if not variants:
                return None

            # A variant missing the flag falls back to the product-level one
            # (False only when every variant is sold out), then to available.
            def is_available(v: dict) -> bool:
                return bool(v.get("available", product.get("available", True)))

            if variant_id:
                # A specific variant was asked for: its own stock state is
                # the answer, in stock or not.
                variant = next((v for v in variants if str(v.get("id")) == variant_id), variants[0])
            else:
                # No ?variant= means the URL names the product, not a size
                # (dickies.com uses one handle per color, ?variant= only picks
                # the size). Sold out only if every variant is; otherwise
                # price the first one that can be bought, not variants[0],
                # which may just be a sold-out size.
                variant = next((v for v in variants if is_available(v)), variants[0])

            raw_price = variant.get("price")
            if cents and isinstance(raw_price, int) and not isinstance(raw_price, bool):
                price = raw_price / 100 if raw_price > 0 else None
            else:
                price = _parse_price(str(raw_price if raw_price is not None else ""))

            if not is_available(variant):
                # Issue #68 — the variant's listed price is kept alongside
                # "oos" (None if it has none, as before).
                return ScraperResult(price=price, status="oos")
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
                    if _og_out_of_stock(soup):
                        # Same shape as the JSON-LD OutOfStock path: the
                        # listed price is kept alongside "oos" (issue #68).
                        return ScraperResult(price=price, status="oos")
                    return ScraperResult(price=price, status="ok")
        return None

    def _extract_nextdata(self, soup: BeautifulSoup, url: str) -> ScraperResult | None:
        return self._lookup_nextdata(soup, url)[0]

    def _lookup_nextdata(self, soup: BeautifulSoup, url: str) -> tuple[ScraperResult | None, bool]:
        """(result, scoped). `scoped` is True when the price came from inside
        the tracked product's own node (or an explicit NEXTDATA_PATHS entry)
        and False when it came from the unscoped whole-page search, which
        also sees carousels, add-ons and banners. _run_hierarchy only lets a
        scoped price replace one found by an earlier tier."""
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return None, False

        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            return None, False

        hostname = urlparse(url).hostname or ""
        explicit_path = NEXTDATA_PATHS.get(hostname)

        if explicit_path:
            try:
                val = reduce(getitem, explicit_path, data)
                price = _parse_price(str(val)) if isinstance(val, str) else (float(val) if isinstance(val, (int, float)) and val > 0 else None)
                if price:
                    return ScraperResult(price=price, status="ok"), True
            except (KeyError, TypeError, IndexError):
                pass

        # ID-scoped priority search (see _find_node_by_id / _PRICE_KEY_PRIORITY
        # docstrings) — falls back to the unscoped whole-tree search when the
        # URL doesn't end in a bare numeric ID, or nothing in the tree
        # carries a matching one. Either way this stays a strict superset of
        # the old "first 'price' key anywhere" behavior, never a regression.
        product_id = _extract_id_from_url(url)
        scope = data
        scoped = False
        if product_id is not None:
            node = _find_node_by_id(data, product_id)
            if node is not None:
                scope = node
                scoped = True

        price = _search_price_by_priority(scope)
        if price:
            return ScraperResult(price=price, status="ok"), scoped
        return None, False

    def _extract_rsc_flight(self, html: str, url: str) -> ScraperResult | None:
        return self._lookup_rsc_flight(html, url)[0]

    def _lookup_rsc_flight(self, html: str, url: str) -> tuple[ScraperResult | None, bool]:
        """NEXT_DATA's App Router counterpart (issue #50) — see
        _parse_rsc_flight_rows/_resolve_rsc_refs docstrings for the wire
        format. No-op ({} rows) on any page without RSC/Flight chunks, so
        this is cheap to always attempt regardless of site. Returns
        (result, scoped) with the same meaning as _lookup_nextdata."""
        rows = _parse_rsc_flight_rows(html)
        if not rows:
            return None, False

        product_id = _extract_id_from_url(url)
        if product_id is not None:
            node = _find_node_by_id(rows, product_id)
            if node is not None:
                # Only the scoped node needs reference resolution — rows
                # matched directly below (unscoped fallback) already have
                # their price key as a direct field (see 29CM's row "a7"),
                # nothing to dereference there.
                resolved = _resolve_rsc_refs(node, rows)
                price = _search_price_by_priority(resolved)
                if price:
                    return ScraperResult(price=price, status="ok"), True

        # No product-id match (or the scoped node had no resolvable price)
        # — same graceful-degradation shape as _extract_nextdata's own
        # id-scoping fallback: search every row directly, unscoped.
        price = _search_price_by_priority(rows)
        if price:
            return ScraperResult(price=price, status="ok"), False
        return None, False

    async def _run_hierarchy(self, html: str, url: str) -> ScraperResult:
        result = await self._extract_shopify(html, url)
        # Which extractor produced `result`, logged at the end so a wrong
        # price is traceable to its source.
        source = "shopify" if result is not None else "none"
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
            if result is not None:
                source = "jsonld"
        if result is None:
            result = self._extract_og_price(soup)
            if result is not None:
                source = "og_price"

        # NEXT_DATA is checked unconditionally now, not only as a last-resort
        # fallback (musinsa regression, this session) — a page can have both
        # a cruder single-value tag (og:price meta, JSON-LD offers.price)
        # *and* a richer __NEXT_DATA__ blob with a real stacked-discount
        # price the cruder tag doesn't know about (musinsa's og:price meta
        # reports its plain sale price; __NEXT_DATA__'s
        # goodsPrice.finalPrice has the coupon-inclusive price on top of
        # that). Whichever succeeded above only gets overridden by a
        # strictly cheaper NEXT_DATA match — never a more expensive one —
        # so a page with no such richer data, or where NEXT_DATA's own
        # price happens to be higher, is unaffected either way.
        #
        # Only a *scoped* match (found inside the tracked product's own node)
        # may replace an earlier tier's price. An unscoped whole-page match
        # can land on an add-on, a carousel item or an installment amount, and
        # "strictly cheaper wins" would then swap in that wrong lower price
        # and fire a false alert. Unscoped still fills in when nothing earlier
        # found a price.
        nextdata_result, nextdata_scoped = self._lookup_nextdata(soup, url)
        if nextdata_result is not None:
            if result is None or (
                nextdata_scoped
                and result.status == "ok"
                and result.price is not None
                and nextdata_result.price < result.price
            ):
                result = nextdata_result
                source = "next_data"
            elif result.status == "ok" and result.price is not None and nextdata_result.price < result.price:
                _log.info(
                    "ignored unscoped next_data price %s (keeping %s from %s) url=%s",
                    nextdata_result.price, result.price, source, url,
                )

        # Same always-compute/override-if-strictly-cheaper pattern as
        # NEXT_DATA just above, for App Router pages that stream RSC/Flight
        # chunks instead of a single __NEXT_DATA__ blob (issue #50, 29CM).
        # A page never has both — _parse_rsc_flight_rows returns {} (this
        # method returns None) on any page without Flight chunks, so this
        # is a no-op on every non-App-Router site, same as NEXT_DATA is a
        # no-op on every site without __NEXT_DATA__.
        rsc_result, rsc_scoped = self._lookup_rsc_flight(html, url)
        if rsc_result is not None:
            if result is None or (
                rsc_scoped
                and result.status == "ok"
                and result.price is not None
                and rsc_result.price < result.price
            ):
                result = rsc_result
                source = "rsc_flight"
            elif result.status == "ok" and result.price is not None and rsc_result.price < result.price:
                _log.info(
                    "ignored unscoped rsc_flight price %s (keeping %s from %s) url=%s",
                    rsc_result.price, result.price, source, url,
                )

        bot_block: str | None = None
        if result is None:
            # Page loaded but no extraction method found a price — silent
            # before issue #53 (no log, no exception), the exact gap that hid
            # #52's Akamai block. Now carries a reason.
            bot_block = _detect_bot_block(soup)
            result = ScraperResult(
                price=None,
                status="error",
                error_reason=bot_block or "no price found on page",
            )

        # Issue #64 — metadata is applied by the scheduler whatever the
        # status, and name inference is first-write-wins, so only attach what
        # the page can legitimately vouch for:
        #   - a detected bot-block / challenge page is not the product: it
        #     has a <title> and a currency heuristic too, none of it ours;
        #   - an "error" page may be anything (a 404, a login wall, a block
        #     page no signature recognises), so its title / site name are
        #     withheld — only the currency (host-derived, harmless) is kept.
        if bot_block is not None:
            _log.info("extractor=none status=error bot_block=%r url=%s", bot_block, url)
            return result
        if result.status == "error":
            site_name = product_title = None
        else:
            site_name = _extract_site_name(soup, jsonld_scripts)
            product_title = _extract_product_title(soup, jsonld_scripts)
            if product_title:
                product_title = _strip_trailing_site_name(product_title, site_name)
        # Unlike site_name/product_title, currency always resolves to a
        # concrete value (CAD default) — no "both None, skip the replace"
        # short-circuit possible here, dataclasses.replace always runs.
        currency, currency_source = _detect_currency(soup, url, jsonld_scripts)
        _log.info(
            "extractor=%s status=%s price=%s currency=%s currency_source=%s url=%s",
            source, result.status, result.price, currency, currency_source, url,
        )
        return dataclasses.replace(
            result, site_name=site_name, product_title=product_title, currency=currency
        )
