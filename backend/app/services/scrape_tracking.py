"""Tracks which Listing ids currently have a scrape in flight (issue #45
follow-up). Purely in-memory, process-local — matches this app's existing
single-instance assumption (same as e.g. PatchrightScraper's class-level
_active_scrapes counter). Not persisted: a restart mid-scrape just loses
track of it, same as any other in-flight work this process was doing.

Exists because compute_status() previously only had one signal for
"processing" — last_scrape_status is None, i.e. "never scraped since
creation." A poll cycle re-scraping an already-scraped listing (scheduled
poll_prices every 6h, or a manual POST /api/poll/prices) had no equivalent
"actively re-scraping right now" signal — the UI just showed the stale
prior status for the whole duration of the re-scrape."""

_in_flight_listing_ids: set[int] = set()


def mark_in_flight(listing_id: int) -> None:
    _in_flight_listing_ids.add(listing_id)


def clear_in_flight(listing_id: int) -> None:
    _in_flight_listing_ids.discard(listing_id)


def in_flight_snapshot() -> set[int]:
    """A copy, not the live set — callers (e.g. compute_status, invoked
    once per product while building an API response) shouldn't observe it
    mutating mid-iteration from a concurrently-running scrape elsewhere."""
    return set(_in_flight_listing_ids)
