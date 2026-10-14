import pytest

from app.schemas.validators import normalize_title


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Apple AirPods Max 2 - Purple", "Apple AirPods Max 2 - Purple"),
        ("  Apple AirPods Max 2 - Purple \n", "Apple AirPods Max 2 - Purple"),
        ("Apple AirPods Max 2 - Purple ", "Apple AirPods Max 2 - Purple"),  # NBSP
        ("Apple AirPods Max 2 - Purple‎", "Apple AirPods Max 2 - Purple"),  # LRM
        ("﻿Apple​ AirPods", "Apple AirPods"),  # BOM + zero-width space
        ("Apple   AirPods\t\nMax", "Apple AirPods Max"),  # internal runs collapse
        ("Family \U0001f468‍\U0001f469‍\U0001f467", "Family \U0001f468‍\U0001f469‍\U0001f467"),  # ZWJ kept
        ("Apple\u00adAirPods\u2060 Max\u202a", "AppleAirPods Max"),  # soft hyphen, word joiner, bidi
        ("   ", None),
        ("‎‏", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_title(raw: str | None, expected: str | None) -> None:
    assert normalize_title(raw) == expected
