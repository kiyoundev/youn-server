import pytest

from app.services.synology import BayState, StorageState


@pytest.fixture
def sample_storage_state() -> StorageState:
    return StorageState(
        bays=[
            BayState(label="1", status="healthy"),
            BayState(label="2", status="empty"),
        ],
        available=5.0,
        used=3.0,
        reserved=0.5,
    )
