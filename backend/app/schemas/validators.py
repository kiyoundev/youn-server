import unicodedata
from urllib.parse import urlparse

_ALLOWED_URL_SCHEMES = {"http", "https"}


def validate_http_url(value: str | None) -> str | None:
    """Reject anything but a well-formed http(s) URL.

    Backend-side mirror of the frontend's isValidUrl() (watchlist/page.tsx) —
    that check only gates the add-item dialog's client-side form and is
    trivially bypassed by anyone calling the API directly (as manual testing
    for #36 did). Without this, a javascript:/data: URL stored via the API
    would render as a clickable <a href> in the table with no further gate.

    `None` passes through untouched — reused by ProductCreate.url and
    ListingUpdate.url, both optional. urlparse(None) raises TypeError, not a
    clean ValidationError, so this must short-circuit before reaching it.
    """
    if value is None:
        return value
    parsed = urlparse(value)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise ValueError(f"url must be http or https, got scheme {parsed.scheme!r}")
    return value


def strip_whitespace(value: str | None) -> str | None:
    """Trim leading/trailing whitespace before it ever reaches the DB.

    Frontend already trims (Add Item dialog, sheet's inline name edit) —
    same reasoning as validate_http_url: that only gates the client-side
    form and is trivially bypassed by anyone calling the API directly.
    `None` passes through untouched — reused by ProductUpdate.name, optional.
    """
    if value is None:
        return value
    return value.strip()


def strip_name_or_none(value: str | None) -> str | None:
    """Same as strip_whitespace, plus: an explicit "" (not just an omitted
    field) also maps to None, not an empty string. Shared by
    ProductCreate.name and ProductUpdate.name (issue #44) — both need "" and
    omitted to mean the same thing (Product.name stays/becomes NULL, so
    process_item's `if product.name is None:` inference guard can still fill
    it later), not two different call sites drifting out of sync on which
    one actually coerces "" and which doesn't."""
    stripped = strip_whitespace(value)
    return stripped or None


# U+200C / U+200D (ZWNJ / ZWJ) are format characters too, but meaningful:
# emoji ZWJ sequences, Persian. Tag characters (U+E0020-E007F) build subdivision
# flag emoji. Everything else in the Unicode "format" category (Cf) is invisible
# and never wanted in a product name: zero-width space, LRM/RLM and the other
# bidi controls, word joiner, soft hyphen, BOM...
_KEEP_FORMAT_CHARS = {"\u200c", "\u200d"}


def _is_invisible(char: str) -> bool:
    if char in _KEEP_FORMAT_CHARS or "\U000e0020" <= char <= "\U000e007f":
        return False
    return unicodedata.category(char) == "Cf"


def normalize_title(value: str | None) -> str | None:
    """Cleans a scraped product title before it is stored as Product.name:
    drops invisible format characters (str.strip()/split() don't treat those
    as whitespace, yet they render as — and copy as — a stray space, e.g. the
    U+200E left-to-right mark retailers append to titles), turns every
    whitespace run (tabs, newlines, NBSP) into one space and trims the ends.
    "" / all-whitespace becomes None.

    Scraped names never pass through the request schemas, so the
    strip_name_or_none validator above never sees them — this is their
    equivalent, applied where the scheduler writes the name (issue #44/#66).
    """
    if value is None:
        return None
    visible = "".join(c for c in value if not _is_invisible(c))
    return " ".join(visible.split()) or None
