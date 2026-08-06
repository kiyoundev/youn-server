from urllib.parse import urlparse

_ALLOWED_URL_SCHEMES = {"http", "https"}


def validate_http_url(value: str) -> str:
    """Reject anything but a well-formed http(s) URL.

    Backend-side mirror of the frontend's isValidUrl() (watchlist/page.tsx) —
    that check only gates the add-item dialog's client-side form and is
    trivially bypassed by anyone calling the API directly (as manual testing
    for #36 did). Without this, a javascript:/data: URL stored via the API
    would render as a clickable <a href> in the table with no further gate.
    """
    parsed = urlparse(value)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise ValueError(f"url must be http or https, got scheme {parsed.scheme!r}")
    return value
