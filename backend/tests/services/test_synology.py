import asyncio

import httpx
import pytest
import respx

from app.core.config import settings
from app.services.synology import SynologyClient

_BASE = "https://fake-nas:5001"

_LOGIN_SUCCESS = lambda sid: httpx.Response(200, json={"success": True, "data": {"sid": sid}})
_STORAGE_ERROR = lambda code: httpx.Response(200, json={"success": False, "error": {"code": code}})
_STORAGE_SUCCESS = httpx.Response(
    200,
    json={
        "success": True,
        "data": {
            "disks": [
                {"slot_id": 1, "status": "normal"},
                {"slot_id": 2, "status": "normal"},
            ],
            "volumes": [
                {"size": {"total": "10000000000000", "used": "3000000000000"}}
            ],
        },
    },
)


@pytest.fixture
def dsm_settings(monkeypatch):
    monkeypatch.setattr(settings, "synology_host", "fake-nas")
    monkeypatch.setattr(settings, "synology_port", 5001)
    monkeypatch.setattr(settings, "synology_use_https", True)
    monkeypatch.setattr(settings, "synology_user", "svc-user")
    monkeypatch.setattr(settings, "synology_password", "svc-pass")
    monkeypatch.setattr(settings, "synology_verify_ssl", False)


@pytest.mark.asyncio
@respx.mock
async def test_first_call_logs_in_and_fetches(dsm_settings) -> None:
    login_route = respx.get(f"{_BASE}/webapi/auth.cgi", params={"method": "login"}).mock(
        return_value=_LOGIN_SUCCESS("sid-1")
    )
    storage_route = respx.get(f"{_BASE}/webapi/entry.cgi", params={"method": "load_info"}).mock(
        return_value=_STORAGE_SUCCESS
    )

    client = SynologyClient()
    state = await client.get_storage()

    assert login_route.call_count == 1
    assert storage_route.call_count == 1
    assert state is not None
    assert state.available == 7.0
    assert state.used == 3.0
    assert state.reserved == 0.0
    assert [b.status for b in state.bays] == ["healthy", "healthy"]


@pytest.mark.asyncio
@respx.mock
async def test_second_call_reuses_cached_sid(dsm_settings) -> None:
    login_route = respx.get(f"{_BASE}/webapi/auth.cgi", params={"method": "login"}).mock(
        return_value=_LOGIN_SUCCESS("sid-1")
    )
    storage_route = respx.get(f"{_BASE}/webapi/entry.cgi", params={"method": "load_info"}).mock(
        return_value=_STORAGE_SUCCESS
    )

    client = SynologyClient()
    await client.get_storage()
    await client.get_storage()

    assert login_route.call_count == 1
    assert storage_route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_session_invalid_triggers_one_relogin_and_retry(dsm_settings) -> None:
    login_route = respx.get(f"{_BASE}/webapi/auth.cgi", params={"method": "login"}).mock(
        side_effect=[_LOGIN_SUCCESS("sid-1"), _LOGIN_SUCCESS("sid-2")]
    )
    storage_route = respx.get(f"{_BASE}/webapi/entry.cgi", params={"method": "load_info"}).mock(
        side_effect=[_STORAGE_ERROR(119), _STORAGE_SUCCESS]
    )

    client = SynologyClient()
    state = await client.get_storage()

    assert login_route.call_count == 2
    assert storage_route.call_count == 2
    assert storage_route.calls[1].request.url.params["_sid"] == "sid-2"
    assert state is not None
    assert state.available == 7.0


@pytest.mark.asyncio
@respx.mock
async def test_non_session_error_does_not_retry(dsm_settings) -> None:
    login_route = respx.get(f"{_BASE}/webapi/auth.cgi", params={"method": "login"}).mock(
        return_value=_LOGIN_SUCCESS("sid-1")
    )
    storage_route = respx.get(f"{_BASE}/webapi/entry.cgi", params={"method": "load_info"}).mock(
        return_value=_STORAGE_ERROR(100)
    )

    client = SynologyClient()
    state = await client.get_storage()

    assert login_route.call_count == 1
    assert storage_route.call_count == 1
    assert state is None


@pytest.mark.asyncio
@respx.mock
async def test_concurrent_calls_only_log_in_once(dsm_settings) -> None:
    async def _slow_login(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return _LOGIN_SUCCESS("sid-1")

    login_route = respx.get(f"{_BASE}/webapi/auth.cgi", params={"method": "login"}).mock(
        side_effect=_slow_login
    )
    storage_route = respx.get(f"{_BASE}/webapi/entry.cgi", params={"method": "load_info"}).mock(
        return_value=_STORAGE_SUCCESS
    )

    client = SynologyClient()
    results = await asyncio.gather(client.get_storage(), client.get_storage())

    assert login_route.call_count == 1
    assert storage_route.call_count == 2
    assert all(r is not None for r in results)


@pytest.mark.asyncio
@respx.mock
async def test_disabled_client_returns_none_without_http_calls() -> None:
    client = SynologyClient()
    state = await client.get_storage()

    assert state is None


@pytest.mark.asyncio
@respx.mock
async def test_close_logs_out_and_clears_sid(dsm_settings) -> None:
    logout_route = respx.get(f"{_BASE}/webapi/auth.cgi", params={"method": "logout"}).mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    client = SynologyClient()
    client._sid = "sid-1"

    await client.close()

    assert logout_route.call_count == 1
    assert logout_route.calls[0].request.url.params["_sid"] == "sid-1"
    assert client._sid is None


@pytest.mark.asyncio
@respx.mock
async def test_close_is_noop_when_no_sid_held(dsm_settings) -> None:
    client = SynologyClient()

    await client.close()

    assert client._sid is None
