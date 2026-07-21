from fastapi import APIRouter, HTTPException

from app.schemas.system import BayResponse, StorageResponse
from app.services.synology import synology_client

router = APIRouter()


@router.get("/api/system/storage", response_model=StorageResponse)
async def get_storage() -> StorageResponse:
    state = await synology_client.get_storage()
    if state is None:
        raise HTTPException(status_code=503, detail="Synology storage data unavailable")
    return StorageResponse(
        bays=[BayResponse(label=b.label, status=b.status) for b in state.bays],
        available=state.available,
        used=state.used,
        reserved=state.reserved,
    )
