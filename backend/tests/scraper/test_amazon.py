"""AmazonCAScraper page-state handling — a sold-out variant redirects to a
different ASIN, and a page with no new offer shows either a used-only buy
box or "See All Buying Options" instead of a price. The HTML fixtures below
are trimmed from real amazon.ca buy-box markup (2026-10-11)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from app.services.scraper.config import AMAZON_MAX_RETRIES
from app.services.scraper.patchright_scraper import (
    AmazonCAScraper,
    PatchrightScraper,
    _amazon_asin,
    _amazon_has_no_new_offer,
    _amazon_new_price,
    _amazon_used_price,
)
from app.services.scraper.result import ScraperResult

_FIXTURES = Path(__file__).parent / "fixtures" / "amazon"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# The tracked URL as pasted from the app (share-link params and all), and
# the different variant Amazon actually served for it.
TRACKED_URL = (
    "https://www.amazon.ca/dp/B0GSS4SGZR?_encoding=UTF8&psc=1"
    "&ref=cm_sw_r_cp_ud_dp_YPHGJGKPZ4C4RRNY0JZG_2&social_share=cm_sw_r_cp_ud_dp_YPHGJGKPZ4C4RRNY0JZG_2"
)
SERVED_OTHER_VARIANT_URL = "https://www.amazon.ca/dp/B0GSS6F226?_encoding=UTF8&th=1"

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
    assert _amazon_has_no_new_offer(_fixture("plain_new.html")) is False


def test_used_only_buy_box_has_no_new_offer() -> None:
    assert _amazon_has_no_new_offer(_fixture("used_only.html")) is True


def test_no_featured_offer_has_no_new_offer() -> None:
    assert _amazon_has_no_new_offer(_fixture("no_featured_offer.html")) is True


def test_classic_out_of_stock_block_has_no_new_offer() -> None:
    assert _amazon_has_no_new_offer('<div id="outOfStock">Currently unavailable.</div>') is True


def test_new_add_to_cart_overrides_stray_markers() -> None:
    """A purchasable new item must never read as out of stock just because a
    used-box or no-offer template also exists somewhere in the DOM."""
    assert _amazon_has_no_new_offer(_fixture("plain_new.html") + _fixture("used_only.html")) is False


def test_both_offers_page_has_a_new_offer() -> None:
    assert _amazon_has_no_new_offer(_fixture("accordion_both.html")) is False


def test_page_with_no_markers_is_not_flagged() -> None:
    assert _amazon_has_no_new_offer("<html><body>captcha page</body></html>") is False


# ── get_price ────────────────────────────────────────────────────────────


def _mock_page(final_url: str, html: str) -> AsyncMock:
    page = AsyncMock()
    page.url = final_url
    page.content = AsyncMock(return_value=html)
    return page


async def _run_get_price(page: AsyncMock, url: str = TRACKED_URL):
    """The page HTML decides everything — prices are parsed from it, nothing
    is patched out except the browser launch and the (Playwright) title read."""
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    scraper = AmazonCAScraper()
    find_title = AsyncMock(return_value="Apple 20W USB-C Power Adapter")
    with (
        patch.object(PatchrightScraper, "start_browser", AsyncMock()),
        patch.object(PatchrightScraper, "_context", context),
        patch.object(AmazonCAScraper, "_find_product_title", find_title),
    ):
        result = await scraper.get_price(url)
    return result, find_title


@pytest.mark.asyncio
async def test_new_buy_box_returns_price() -> None:
    page = _mock_page(TRACKED_URL, _fixture("plain_new.html"))

    result, _ = await _run_get_price(page)

    assert result == ScraperResult(
        price=88.0, status="ok", product_title="Apple 20W USB-C Power Adapter", currency="CAD"
    )


@pytest.mark.asyncio
async def test_both_offers_page_returns_the_new_price_not_the_used_one() -> None:
    page = _mock_page(TRACKED_URL, _fixture("accordion_both.html"))

    result, _ = await _run_get_price(page)

    assert result.status == "ok"
    assert result.price == 54.98
    assert result.used_price is None


@pytest.mark.asyncio
async def test_redirect_to_another_variant_is_oos_and_never_reads_its_price() -> None:
    """The real case: the tracked ASIN redirected to a variant whose page is
    a used-only box — that is another color's price, not ours (new or used)."""
    page = _mock_page(SERVED_OTHER_VARIANT_URL, _fixture("used_only.html"))

    result, find_title = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="oos", currency="CAD", used_price=None)
    find_title.assert_not_awaited()
    page.goto.assert_awaited()  # retries are not burned: one attempt, one visit pair
    assert page.close.await_count == 1


@pytest.mark.asyncio
async def test_used_only_buy_box_on_same_asin_is_oos_for_new_with_the_used_price() -> None:
    page = _mock_page(TRACKED_URL, _fixture("used_only.html"))

    result, find_title = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="oos", currency="CAD", used_price=637.19)
    find_title.assert_not_awaited()


@pytest.mark.asyncio
async def test_see_all_buying_options_is_oos_not_exhausted_retries() -> None:
    page = _mock_page(TRACKED_URL, _fixture("no_featured_offer.html"))

    result, _ = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="oos", currency="CAD", used_price=None)
    assert page.content.await_count == 1  # no retries burned


@pytest.mark.asyncio
async def test_url_without_asin_skips_the_redirect_check() -> None:
    """Short links / captcha pages have no ASIN to compare — fall through to
    the normal price read rather than guessing a redirect."""
    page = _mock_page("https://www.amazon.ca/dp/B0DJFW7PNM", _fixture("plain_new.html"))

    result, _ = await _run_get_price(page, url="https://a.co/d/abc123")

    assert result.status == "ok"
    assert result.price == 88.0


@pytest.mark.asyncio
async def test_unrecognized_page_without_price_still_exhausts_retries() -> None:
    """A page that is neither a known no-offer state nor has a new buy box
    (e.g. a captcha) is still a scrape failure, not a stock status."""
    page = _mock_page(TRACKED_URL, "<html><body>robot check</body></html>")

    result, _ = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="error", error_reason="exhausted retries")
    assert page.content.await_count == AMAZON_MAX_RETRIES


@pytest.mark.asyncio
async def test_new_buy_box_without_a_readable_price_is_a_named_error() -> None:
    """A purchasable new item whose price can't be read from inside the buy
    box must surface as an error — never the page-wide fallback's guess, and
    never oos (that would fake a restock on the next good read)."""
    html = '<div><input id="add-to-cart-button" type="submit"></div><span class="a-offscreen">$99.99</span>'
    page = _mock_page(TRACKED_URL, html)

    result, find_title = await _run_get_price(page)

    assert result == ScraperResult(price=None, status="error", error_reason="price not found in the new buy box")
    assert page.content.await_count == AMAZON_MAX_RETRIES
    find_title.assert_not_awaited()


# ── price parsers (issue #60) ────────────────────────────────────────────
# Real, trimmed amazon.ca markup lives in fixtures/amazon/ (see each file's
# header comment for the ASIN it came from).

@pytest.mark.parametrize(
    "fixture, expected",
    [
        ("plain_new.html", 88.0),
        ("import_fees_new.html", 58.7),
        ("accordion_both.html", 54.98),
    ],
)
def test_new_price_is_read_from_the_new_buy_box(fixture: str, expected: float) -> None:
    assert _amazon_new_price(_fixture(fixture)) == expected


def test_new_price_does_not_depend_on_row_order() -> None:
    """The used row placed BEFORE the new row must still not win: the read is
    anchored on the new add-to-cart button, not on document order."""
    soup = BeautifulSoup(_fixture("accordion_both.html"), "html.parser")
    used_row = soup.find(id="usedAccordionRow").extract()
    soup.find(id="newAccordionRow_0").insert_before(used_row)

    assert _amazon_new_price(str(soup)) == 54.98


def test_both_offers_page_never_returns_the_used_row_price() -> None:
    html = _fixture("accordion_both.html")
    assert _amazon_new_price(html) != 52.13  # the used row sits in the same page
    assert _amazon_used_price(html) is None  # and it is not the used-only box


@pytest.mark.parametrize("fixture", ["used_only.html", "no_featured_offer.html"])
def test_no_new_price_when_the_page_has_no_new_add_to_cart(fixture: str) -> None:
    """The used-only page still shows $637.19 in its title price label and in a
    hidden customerVisiblePrice input — neither is a new price."""
    assert _amazon_new_price(_fixture(fixture)) is None


def test_used_price_is_read_from_the_used_only_box() -> None:
    assert _amazon_used_price(_fixture("used_only.html")) == 637.19


@pytest.mark.parametrize("fixture", ["plain_new.html", "import_fees_new.html", "accordion_both.html", "no_featured_offer.html"])
def test_no_used_price_without_a_used_only_box(fixture: str) -> None:
    assert _amazon_used_price(_fixture(fixture)) is None


def test_decoy_amounts_next_to_the_price_are_not_read() -> None:
    """Delivery ($7.28), import-fee breakdown ($51.94 / $6.76) and the "Other
    sellers" price ($12.34) all sit on the page; only the price-to-pay node counts."""
    assert _amazon_new_price(_fixture("import_fees_new.html")) == 58.7
    assert _amazon_new_price(_fixture("plain_new.html")) == 88.0


_BUTTON = '<input id="add-to-cart-button" type="submit" value="Add to cart">'


def test_empty_price_text_falls_back_to_the_forms_amount() -> None:
    html = (
        '<form id="addToCart">'
        '<input type="hidden" name="items[0.base][customerVisiblePrice][amount]" value="12.5">'
        '<div><span class="a-price apex-pricetopay-value"><span class="a-offscreen"></span></span>'
        f"{_BUTTON}</div></form>"
        '<span class="a-offscreen">$99.99</span>'
    )
    assert _amazon_new_price(html) == 12.5


def test_title_label_text_is_never_parsed_as_a_price() -> None:
    """data-pricetopay-label spans carry "$X with N percent savings", which the
    shared parser turns into garbage — and reflect the featured offer, which can
    be used. Only the price-to-pay node (or the form amount) is trusted."""
    html = (
        '<span id="apex-pricetopay-accessibility-label" data-pricetopay-label="{priceToPay}">'
        "$52.13 with 5 percent savings</span>"
        f'<form id="addToCart">{_BUTTON}</form>'
    )
    assert _amazon_new_price(html) is None


def test_price_outside_the_buy_box_ancestry_is_not_read() -> None:
    """A price that shares nothing with the add-to-cart button except the whole
    page is not "in the buy box" — better an error than a guessed price."""
    html = f'<div>{_BUTTON}</div><span class="a-price apex-pricetopay-value"><span class="a-offscreen">$99.99</span></span>'
    assert _amazon_new_price(html) is None


def test_only_the_exact_add_to_cart_id_counts_as_new() -> None:
    html = (
        '<div><span class="a-price apex-pricetopay-value"><span class="a-offscreen">$52.13</span></span>'
        '<input id="add-to-cart-button-ubb" type="submit"></div>'
    )
    assert _amazon_new_price(html) is None


def test_non_numeric_amount_is_not_a_price() -> None:
    html = (
        '<form id="addToCart">'
        '<input type="hidden" name="items[0.base][customerVisiblePrice][amount]" value="n/a">'
        f"<div>{_BUTTON}</div></form>"
    )
    assert _amazon_new_price(html) is None


def test_used_price_skips_empty_offer_price_nodes() -> None:
    html = (
        '<div id="usedBuySection">'
        '<span class="offer-price"></span><span class="offer-price">$12.00</span></div>'
    )
    assert _amazon_used_price(html) == 12.0
