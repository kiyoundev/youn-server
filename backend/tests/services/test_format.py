from app.services.format import format_price


def test_format_price_krw_no_decimals_thousands_separator():
    assert format_price(388000.0, "KRW") == "₩388,000"


def test_format_price_krw_rounds():
    assert format_price(999.6, "KRW") == "₩1,000"


def test_format_price_usd_has_suffix():
    assert format_price(89.99, "USD") == "$89.99 USD"


def test_format_price_cad_no_suffix():
    assert format_price(89.99, "CAD") == "$89.99"


def test_format_price_none_currency_matches_cad_output():
    # Unresolved currency — matches the pre-#45 always-"$" behavior for the
    # window before a product's currency has been detected.
    assert format_price(89.99, None) == "$89.99"
