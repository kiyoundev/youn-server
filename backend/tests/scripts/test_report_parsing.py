from _report_parsing import extract_executive_summary, extract_price_target


def test_extract_price_target_found():
    markdown = "**Rating**: Buy\n\n**Executive Summary**: Text here.\n\n**Price Target**: 123.45"
    assert extract_price_target(markdown) == 123.45


def test_extract_price_target_missing():
    markdown = "**Rating**: Hold\n\n**Executive Summary**: No target given."
    assert extract_price_target(markdown) is None


def test_extract_price_target_integer_value():
    markdown = "**Price Target**: 200"
    assert extract_price_target(markdown) == 200.0


def test_extract_price_target_negative_value():
    markdown = "**Price Target**: -12.5"
    assert extract_price_target(markdown) == -12.5


def test_extract_executive_summary_found():
    markdown = (
        "**Rating**: Buy\n\n"
        "**Executive Summary**: Enter now, size small, watch the 200 level.\n\n"
        "**Investment Thesis**: Long detailed reasoning follows."
    )
    assert (
        extract_executive_summary(markdown)
        == "Enter now, size small, watch the 200 level."
    )


def test_extract_executive_summary_at_end_of_string():
    markdown = "**Rating**: Sell\n\n**Executive Summary**: This is the last section."
    assert extract_executive_summary(markdown) == "This is the last section."


def test_extract_executive_summary_missing():
    markdown = "**Rating**: Hold"
    assert extract_executive_summary(markdown) is None


def test_extract_executive_summary_multiline():
    markdown = (
        "**Executive Summary**: Line one of the summary.\n"
        "Line two of the summary.\n\n"
        "**Price Target**: 50.0"
    )
    assert extract_executive_summary(markdown) == (
        "Line one of the summary.\nLine two of the summary."
    )
