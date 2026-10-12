"""AmazonCAScraper page-state handling — a sold-out variant redirects to a
different ASIN, and a page with no new offer shows either a used-only buy
box or "See All Buying Options" instead of a price. The HTML fixtures below
are trimmed from real amazon.ca buy-box markup (2026-10-11)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scraper.config import AMAZON_MAX_RETRIES
from app.services.scraper.patchright_scraper import (
    AmazonCAScraper,
    PatchrightScraper,
    _amazon_asin,
    _amazon_has_no_new_offer,
)
from app.services.scraper.result import ScraperResult

# The tracked URL as pasted from the app (share-link params and all), and
# the different variant Amazon actually served for it.
TRACKED_URL = (
    "https://www.amazon.ca/dp/B0GSS4SGZR?_encoding=UTF8&psc=1"
    "&ref=cm_sw_r_cp_ud_dp_YPHGJGKPZ4C4RRNY0JZG_2&social_share=cm_sw_r_cp_ud_dp_YPHGJGKPZ4C4RRNY0JZG_2"
)
SERVED_OTHER_VARIANT_URL = "https://www.amazon.ca/dp/B0GSS6F226?_encoding=UTF8&th=1"

NEW_BUYBOX_HTML = """
<div id="desktop_qualifiedBuyBox">
  <div id="corePrice_feature_div">
    <span id="apex-pricetopay-accessibility-label" data-pricetopay-label="{priceToPay}"
          class="aok-offscreen"> $24.99 </span>
  </div>
  <div id="availability"><span class="primary-availability-message"> In Stock </span></div>
  <input id="add-to-cart-button" name="submit.add-to-cart" type="submit" value="Add to cart">
</div>
"""

USED_ONLY_HTML = """
<div id="usedOnlyBuybox" class="a-section a-spacing-medium">
  <div id="usedBuySection" class="rbbHeader dp-accordion-row">
    <span class="a-text-bold">Buy Used :</span>
    <span class="a-size-base a-color-price offer-price a-text-normal">$637.25</span>
  </div>
  <div id="usedbuyBox">
    <strong>Used: Like New</strong>
    <a id="sellerProfileTriggerId">Warehouse Deals</a>
    <div id="availability"><span class="primary-availability-message"> Only 1 left in stock. </span></div>
    <input id="add-to-cart-button-ubb" name="submit.add-to-cart-ubb" type="submit" value="Add to cart">
  </div>
</div>
"""

NO_FEATURED_OFFER_HTML = """
<div id="fod-cx-box" class="a-box"><span>No featured offers available<br></span></div>
<div id="unqualifiedBuyBox" class="a-box">
  <span id="buybox-see-all-buying-choices" class="a-button">
    <a href="/gp/offer-listing/B0GSRYXZM5/ref=dp_olp_unknown_mbc" title="See All Buying Options">See All Buying Options</a>
  </span>
</div>
"""


# ── _amazon_asin ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected",
    [
        (TRACKED_URL, "B0GSS4SGZR"),
        (SERVED_OTHER_VARIANT_URL, "B0GSS6F226"),
        ("https://www.amazon.ca/Apple-Charger/dp/B0DJFW7PNM/ref=sr_1_1", "B0DJFW7PNM"),
        ("https://www.amazon.ca/gp/product/B0DJFW7PNM?th=1", "B0DJFW7PNM"),
        ("https://a.co/d/abc123", None),
        ("https://www.amazon.ca/errors/validateCaptcha", None),
    ],
)
def test_amazon_asin(url: str, expected: str | None) -> None:
    assert _amazon_asin(url) == expected


def test_amazon_asin_ignores_asin_lookalikes_in_query_string() -> None:
    assert _amazon_asin("https://www.amazon.ca/dp/B0GSS4SGZR?ref=/dp/B0AAAAAAAA") == "B0GSS4SGZR"


# ── _amazon_has_no_new_offer ─────────────────────────────────────────────


def test_new_buy_box_has_a_new_offer() -> None:
    assert _amazon_has_no_new_offer(NEW_BUYBOX_HTML) is False


def test_used_only_buy_box_has_no_new_offer() -> None:
    assert _amazon_has_no_new_offer(USED_ONLY_HTML) is True


def test_no_featured_offer_has_no_new_offer() -> None:
    assert _amazon_has_no_new_offer(NO_FEATURED_OFFER_HTML) is True


def test_classic_out_of_stock_block_has_no_new_offer() -> None:
    assert _amazon_has_no_new_offer('<div id="outOfStock">Currently unavailable.</div>') is True


def test_new_add_to_cart_overrides_stray_markers() -> None:
    """A purchasable new item must never read as out of stock just because a
    used-box or no-offer template also exists somewhere in the DOM."""
    assert _amazon_has_no_new_offer(NEW_BUYBOX_HTML + USED_ONLY_HTML) is False


def test_page_with_no_markers_is_not_flagged() -> None:
    assert _amazon_has_no_new_offer("<html><body>captcha page</body></html>") is False


# ── get_price ────────────────────────────────────────────────────────────


def _mock_page(final_url: str, html: str) -> AsyncMock:
    page = AsyncMock()
    page.url = final_url
    page.content = AsyncMock(return_value=html)
    return page


async def _run_get_price(page: AsyncMock, url: str = TRACKED_URL, price_text: str | None = "$24.99"):
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    scraper = AmazonCAScraper()
    find_price = AsyncMock(return_value=price_text)
    find_title = AsyncMock(return_value="Apple 20W USB-C Power Adapter")
    with (
        patch.object(PatchrightScraper, "start_browser", AsyncMock()),
        patch.object(PatchrightScraper, "_context", context),
        patch.object(AmazonCAScraper, "_find_price_text", find_price),
        patch.object(AmazonCAScraper, "_find_product_title", find_title),
    ):
        result = await scraper.get_price(url)
    return result, find_price


@pytest.mark.asyncio
async def test_new_buy_box_returns_price() -> None:
    page = _mock_page(TRACKED_URL, NEW_BUYBOX_HTML)

    result, _ = await _run_get_price(page)

    assert result == ScraperResult(
        price=24.99, status="ok", product_title="Apple 20W USB-C Power Adapter", currency="CAD"
    )


@pytest.mark.asyncio
async def test_redirect_to_another_variant_is_oos_and_never_reads_its_price() -> None:
    """The real case: the tracked ASIN redirected to a variant whose page is
    a used-only box at $637.25 — that is another color's price, not ours."""
    page = _mock_page(SERVED_OTHER_VARIANT_URL, USED_ONLY_HTML)

    result, find_price = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="oos", currency="CAD")
    find_price.assert_not_awaited()
    page.goto.assert_awaited()  # retries are not burned: one attempt, one visit pair
    assert page.close.await_count == 1


@pytest.mark.asyncio
async def test_used_only_buy_box_on_same_asin_is_oos_for_new() -> None:
    page = _mock_page(TRACKED_URL, USED_ONLY_HTML)

    result, find_price = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="oos", currency="CAD")
    find_price.assert_not_awaited()


@pytest.mark.asyncio
async def test_see_all_buying_options_is_oos_not_exhausted_retries() -> None:
    page = _mock_page(TRACKED_URL, NO_FEATURED_OFFER_HTML)

    result, find_price = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="oos", currency="CAD")
    find_price.assert_not_awaited()


@pytest.mark.asyncio
async def test_url_without_asin_skips_the_redirect_check() -> None:
    """Short links / captcha pages have no ASIN to compare — fall through to
    the normal price read rather than guessing a redirect."""
    page = _mock_page("https://www.amazon.ca/dp/B0DJFW7PNM", NEW_BUYBOX_HTML)

    result, _ = await _run_get_price(page, url="https://a.co/d/abc123")

    assert result.status == "ok"
    assert result.price == 24.99


@pytest.mark.asyncio
async def test_unrecognized_page_without_price_still_exhausts_retries() -> None:
    """A page that is neither a known no-offer state nor has a price (e.g.
    a captcha) is still a scrape failure, not a stock status."""
    page = _mock_page(TRACKED_URL, "<html><body>robot check</body></html>")

    result, find_price = await _run_get_price(page, price_text=None)

    assert result == ScraperResult(price=None, status="error", error_reason="exhausted retries")
    assert find_price.await_count == AMAZON_MAX_RETRIES
