from dataclasses import asdict, fields
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.positions import PositionResponse
from app.services.portfolio import PositionRow


def test_position_out_has_exactly_the_fields_of_position_row() -> None:
    # the route maps rows with PositionResponse(**asdict(row)); a drifting field
    # name would fail there at request time, so catch it here
    assert set(PositionResponse.model_fields) == {f.name for f in fields(PositionRow)}


def test_row_maps_to_position_out_and_serializes_as_iso() -> None:
    at = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
    row = PositionRow("NVDA", "USD", 15, 110.0, 1650.0, 120.0, "ok", at, 1800.0, 150.0, 150 / 1650)

    out = PositionResponse(**asdict(row))

    assert out.model_dump(mode="json")["price_as_of"] == "2026-10-26T14:00:00Z"


def test_unpriced_row_keeps_none_fields() -> None:
    row = PositionRow("SOFI", "USD", 20, 8.25, 165.0, None, "unavailable", None, None, None, None)

    out = PositionResponse(**asdict(row))

    assert (out.current_price, out.price_as_of, out.unrealized_gain_pct) == (None, None, None)


def test_unknown_currency_or_status_is_rejected() -> None:
    base = dict(
        symbol="X", shares=1, avg_cost=1.0, invested=1.0, current_price=None,
        price_as_of=None, market_value=None, unrealized_gain=None, unrealized_gain_pct=None,
    )
    with pytest.raises(ValidationError):
        PositionResponse(**base, native_currency="KRW", price_status="ok")
    with pytest.raises(ValidationError):
        PositionResponse(**base, native_currency="USD", price_status="fresh")
