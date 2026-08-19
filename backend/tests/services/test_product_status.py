import datetime as dt
from types import SimpleNamespace

from app.services.product_status import compute_last_checked, compute_status


def _listing(*, last_scrape_status: str | None = "ok") -> SimpleNamespace:
    return SimpleNamespace(last_scrape_status=last_scrape_status)


def test_compute_status_product_inactive_is_paused() -> None:
    listings = [_listing(), _listing()]

    assert compute_status(listings, product_active=False, alerted_at=None) == "paused"


def test_compute_status_no_listings_is_paused() -> None:
    assert compute_status([], product_active=False, alerted_at=None) == "paused"


def test_compute_status_active_listing_errored_is_failed() -> None:
    listings = [_listing(last_scrape_status="ok"), _listing(last_scrape_status="error")]

    assert compute_status(listings, product_active=True, alerted_at=None) == "failed"


def test_compute_status_alerted_is_triggered() -> None:
    listings = [_listing(last_scrape_status="ok")]

    assert compute_status(listings, product_active=True, alerted_at=dt.datetime.now(dt.timezone.utc)) == "triggered"


def test_compute_status_failed_outranks_triggered() -> None:
    """Priority order: paused > failed > triggered > watching."""
    listings = [_listing(last_scrape_status="error")]

    assert compute_status(listings, product_active=True, alerted_at=dt.datetime.now(dt.timezone.utc)) == "failed"


def test_compute_status_default_watching() -> None:
    listings = [_listing(last_scrape_status="ok"), _listing(last_scrape_status="oos")]

    assert compute_status(listings, product_active=True, alerted_at=None) == "watching"


def test_compute_status_never_scraped_listing_is_processing() -> None:
    listings = [_listing(last_scrape_status=None)]

    assert compute_status(listings, product_active=True, alerted_at=None) == "processing"


def test_compute_status_processing_outranks_failed() -> None:
    """A never-scraped listing shouldn't be masked by a sibling's past
    error — see .plan/41-immediate-first-scrape's acceptance criteria."""
    listings = [_listing(last_scrape_status="error"), _listing(last_scrape_status=None)]

    assert compute_status(listings, product_active=True, alerted_at=None) == "processing"


def test_compute_status_processing_outranks_triggered() -> None:
    """A freshly-added listing on an already-triggered product should read
    as processing until it reports, not stay stuck on stale 'triggered'."""
    listings = [_listing(last_scrape_status="ok"), _listing(last_scrape_status=None)]

    assert compute_status(listings, product_active=True, alerted_at=dt.datetime.now(dt.timezone.utc)) == "processing"


def test_compute_status_paused_outranks_processing() -> None:
    """Product-inactive still wins even if the sole listing was never
    scraped — 'paused' short-circuits before the processing check ever
    runs."""
    listings = [_listing(last_scrape_status=None)]

    assert compute_status(listings, product_active=False, alerted_at=None) == "paused"


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
