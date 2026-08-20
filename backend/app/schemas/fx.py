from datetime import datetime

from pydantic import BaseModel


class FxRatesResponse(BaseModel):
    """GET /api/fx-rates' response shape (issue #45). rates: {"USD": 1.35,
    "KRW": 0.00098} — CAD is implicit 1.0, never stored/returned as a row.
    stale: True if either expected currency's row is missing entirely
    (never fetched yet) or its fetched_at is older than 24h. fetched_at:
    the *older* of the two rows' fetched_at values (the more stale one is
    what determines trustworthiness), None if no rows exist yet."""

    rates: dict[str, float]
    stale: bool
    fetched_at: datetime | None
