from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import system


@pytest.mark.asyncio
async def test_get_storage_route_returns_matching_shape(monkeypatch, sample_storage_state) -> None:
    monkeypatch.setattr(
        system.synology_client, "get_storage", AsyncMock(return_value=sample_storage_state)
    )

    result = await system.get_storage()

    assert result.available == sample_storage_state.available
    assert result.used == sample_storage_state.used
    assert result.reserved == sample_storage_state.reserved
    assert [b.label for b in result.bays] == ["1", "2"]
    assert [b.status for b in result.bays] == ["healthy", "empty"]


@pytest.mark.asyncio
async def test_get_storage_route_raises_503_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(system.synology_client, "get_storage", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await system.get_storage()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Synology storage data unavailable"
