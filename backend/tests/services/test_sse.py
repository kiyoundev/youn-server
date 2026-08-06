import asyncio
import json

import pytest

from app.services import sse


@pytest.fixture(autouse=True)
def _reset_fanout():
    """`sse._clients` is module-level, shared across the whole test session —
    clear it before and after every test so one test's registrations can
    never leak into the next."""
    sse._clients.clear()
    yield
    sse._clients.clear()


def test_register_adds_a_new_queue_to_the_fanout_set() -> None:
    queue = sse.register()
    assert queue in sse._clients
    assert len(sse._clients) == 1


def test_register_returns_a_distinct_queue_per_call() -> None:
    q1 = sse.register()
    q2 = sse.register()
    assert q1 is not q2
    assert len(sse._clients) == 2


def test_unregister_removes_the_queue() -> None:
    queue = sse.register()
    sse.unregister(queue)
    assert queue not in sse._clients
    assert len(sse._clients) == 0


def test_unregister_is_safe_to_call_twice() -> None:
    queue = sse.register()
    sse.unregister(queue)
    sse.unregister(queue)  # must not raise
    assert len(sse._clients) == 0


def test_unregister_of_a_never_registered_queue_is_a_noop() -> None:
    sse.unregister(asyncio.Queue())  # never registered
    assert len(sse._clients) == 0


def test_broadcast_with_no_clients_does_not_raise() -> None:
    sse.broadcast({"product_id": 1, "listing_id": 2})
    assert len(sse._clients) == 0


def test_broadcast_delivers_serialized_payload_to_a_registered_client() -> None:
    queue = sse.register()
    sse.broadcast({"product_id": 1, "listing_id": 2})

    assert queue.qsize() == 1
    assert json.loads(queue.get_nowait()) == {"product_id": 1, "listing_id": 2}


def test_broadcast_delivers_independent_copies_to_every_registered_client() -> None:
    q1 = sse.register()
    q2 = sse.register()
    sse.broadcast({"product_id": 5, "listing_id": 9})

    assert json.loads(q1.get_nowait()) == {"product_id": 5, "listing_id": 9}
    assert json.loads(q2.get_nowait()) == {"product_id": 5, "listing_id": 9}


def test_broadcast_does_not_reach_a_client_that_already_unregistered() -> None:
    queue = sse.register()
    sse.unregister(queue)
    sse.broadcast({"product_id": 1, "listing_id": 2})
    assert queue.empty()
