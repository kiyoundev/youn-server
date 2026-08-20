from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import fx
from app.models.fx_rate import FxRate


def _db(rows: list[FxRate]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_get_fx_rates_empty_table_returns_stale_with_empty_rates() -> None:
    # Bootstrap case (schema.md) — before the first successful
    # refresh_fx_rates, this is a normal response shape, not an error.
    result = await fx.get_fx_rates(db=_db([]))

    assert result.rates == {}
    assert result.stale is True
    assert result.fetched_at is None


@pytest.mark.asyncio
async def test_get_fx_rates_fresh_rows_not_stale() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        FxRate(currency="USD", rate_to_cad=1.35, fetched_at=now),
        FxRate(currency="KRW", rate_to_cad=0.00098, fetched_at=now),
    ]
    result = await fx.get_fx_rates(db=_db(rows))

    assert result.rates == {"USD": 1.35, "KRW": 0.00098}
    assert result.stale is False
    assert result.fetched_at == now


@pytest.mark.asyncio
async def test_get_fx_rates_one_row_older_than_24h_is_stale() -> None:
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(hours=25)
    rows = [
        FxRate(currency="USD", rate_to_cad=1.35, fetched_at=now),
        FxRate(currency="KRW", rate_to_cad=0.00098, fetched_at=stale_time),
    ]
    result = await fx.get_fx_rates(db=_db(rows))

    assert result.stale is True
    # Older of the two fetched_at values, since it's the one that
    # determines trustworthiness.
    assert result.fetched_at == stale_time


@pytest.mark.asyncio
async def test_get_fx_rates_one_row_entirely_missing_is_stale() -> None:
    now = datetime.now(timezone.utc)
    # Only USD ever successfully fetched — KRW row doesn't exist at all.
    rows = [FxRate(currency="USD", rate_to_cad=1.35, fetched_at=now)]
    result = await fx.get_fx_rates(db=_db(rows))

    assert result.rates == {"USD": 1.35}
    assert result.stale is True
    assert result.fetched_at == now


@pytest.mark.asyncio
async def test_get_fx_rates_23h_old_row_not_stale() -> None:
    now = datetime.now(timezone.utc)
    fresh_enough = now - timedelta(hours=23)
    rows = [
        FxRate(currency="USD", rate_to_cad=1.35, fetched_at=fresh_enough),
        FxRate(currency="KRW", rate_to_cad=0.00098, fetched_at=fresh_enough),
    ]
    result = await fx.get_fx_rates(db=_db(rows))

    assert result.stale is False
