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
