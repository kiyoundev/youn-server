import datetime as dt
from types import SimpleNamespace

from app.services.product_status import compute_last_checked, compute_status


def _listing(*, active: bool = True, last_scrape_status: str | None = "ok") -> SimpleNamespace:
    return SimpleNamespace(active=active, last_scrape_status=last_scrape_status)


def test_compute_status_all_inactive_is_paused() -> None:
    listings = [_listing(active=False), _listing(active=False)]

    assert compute_status(listings, alerted_at=None) == "paused"


def test_compute_status_no_listings_is_paused() -> None:
    assert compute_status([], alerted_at=None) == "paused"


def test_compute_status_active_listing_errored_is_failed() -> None:
    listings = [_listing(last_scrape_status="ok"), _listing(last_scrape_status="error")]

    assert compute_status(listings, alerted_at=None) == "failed"


def test_compute_status_inactive_listing_error_does_not_count() -> None:
    """An errored listing that's paused shouldn't drag the product into
    'failed' — only active listings' scrape health matters."""
    listings = [_listing(active=True, last_scrape_status="ok"), _listing(active=False, last_scrape_status="error")]

    assert compute_status(listings, alerted_at=None) == "watching"


def test_compute_status_alerted_is_triggered() -> None:
    listings = [_listing(last_scrape_status="ok")]

    assert compute_status(listings, alerted_at=dt.datetime.now(dt.timezone.utc)) == "triggered"


def test_compute_status_failed_outranks_triggered() -> None:
    """Priority order: paused > failed > triggered > watching."""
    listings = [_listing(last_scrape_status="error")]

    assert compute_status(listings, alerted_at=dt.datetime.now(dt.timezone.utc)) == "failed"


def test_compute_status_default_watching() -> None:
    listings = [_listing(last_scrape_status="ok"), _listing(last_scrape_status="oos")]

    assert compute_status(listings, alerted_at=None) == "watching"


def test_compute_last_checked_returns_stalest() -> None:
    older = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    newer = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)

    assert compute_last_checked([newer, older]) == older


def test_compute_last_checked_ignores_none_unless_all_none() -> None:
    known = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

    assert compute_last_checked([None, known]) == known


def test_compute_last_checked_all_none_returns_none() -> None:
    assert compute_last_checked([None, None]) is None


def test_compute_last_checked_empty_returns_none() -> None:
    assert compute_last_checked([]) is None
