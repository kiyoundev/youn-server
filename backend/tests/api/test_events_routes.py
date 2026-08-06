import asyncio

import pytest
from app.api import events
from app.core.config import settings
from app.main import app
from app.services import sse
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_fanout():
    sse._clients.clear()
    yield
    sse._clients.clear()


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "api_key", "secret-test-key")
    return TestClient(app, raise_server_exceptions=False)


def test_stream_requires_api_key(client: TestClient) -> None:
    response = client.get("/api/events/stream")
    assert response.status_code == 401


def test_stream_wrong_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/api/events/stream", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


# The tests below drive `_event_generator()` directly rather than through
# TestClient's streaming response — TestClient's ASGI app runs in a
# background thread, and racing `sse.broadcast()` (called from the test's
# own thread) against `asyncio.Queue` operations on that other thread's loop
# is exactly the kind of thread-unsafe interaction this suite shouldn't rely
# on. Calling the generator directly keeps everything on one event loop, and
# still exercises the same register/yield/unregister code the route uses.


@pytest.mark.asyncio
async def test_event_generator_registers_before_first_yield(monkeypatch) -> None:
    monkeypatch.setattr(events, "_PING_INTERVAL", 0.01)
    assert len(sse._clients) == 0

    gen = events._event_generator()
    chunk = await gen.__anext__()  # first ping — proves register() already ran

    assert chunk == ": ping\n\n"
    assert len(sse._clients) == 1

    await gen.aclose()


@pytest.mark.asyncio
async def test_event_generator_unregisters_on_explicit_close(monkeypatch) -> None:
    monkeypatch.setattr(events, "_PING_INTERVAL", 0.01)
    gen = events._event_generator()
    await gen.__anext__()  # register() runs; first ping consumed
    assert len(sse._clients) == 1

    await gen.aclose()
    assert len(sse._clients) == 0


@pytest.mark.asyncio
async def test_event_generator_yields_ping_on_idle_timeout(monkeypatch) -> None:
    monkeypatch.setattr(events, "_PING_INTERVAL", 0.01)
    gen = events._event_generator()

    first = await gen.__anext__()
    second = await gen.__anext__()

    assert first == ": ping\n\n"
    assert second == ": ping\n\n"
    await gen.aclose()


@pytest.mark.asyncio
async def test_event_generator_yields_broadcast_payload_before_any_ping(monkeypatch) -> None:
    monkeypatch.setattr(events, "_PING_INTERVAL", 5)  # long enough that only the broadcast triggers a yield
    gen = events._event_generator()

    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.01)  # let the generator register + start waiting on its own queue
    sse.broadcast({"product_id": 1, "listing_id": 2})

    chunk = await asyncio.wait_for(task, timeout=1)

    assert chunk == 'data: {"product_id": 1, "listing_id": 2}\n\n'
    await gen.aclose()


@pytest.mark.asyncio
async def test_event_generator_unregisters_when_the_consuming_task_is_cancelled(monkeypatch) -> None:
    """Simulates a real client disconnect: Starlette cancels/tears down the
    generator's driving task rather than calling aclose() directly."""
    monkeypatch.setattr(events, "_PING_INTERVAL", 5)
    gen = events._event_generator()

    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.01)
    assert len(sse._clients) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(sse._clients) == 0
