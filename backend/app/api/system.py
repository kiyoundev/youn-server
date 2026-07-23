from fastapi import APIRouter, HTTPException

from app.schemas.system import BayResponse, StorageResponse
from app.services.synology import synology_client

router = APIRouter()


@router.get(
    "/api/system/storage",
    response_model=StorageResponse,
    summary="Get Synology NAS storage status",
    description=(
        "Reads bay/volume health directly from the NAS over DSM's webapi "
        "(`SYNO.Storage.CGI.Storage`) — no caching, one live DSM session per call."
    ),
)
async def get_storage() -> StorageResponse:
    """Fetch live storage and bay health from the Synology NAS.

    Returns:
        Per-bay status (`healthy`/`warning`/`error`/`empty`) plus
        available/used/reserved capacity in TB.

    Raises:
        HTTPException: 503 if Synology credentials are unset or the NAS is
            unreachable.
    """
    state = await synology_client.get_storage()
    if state is None:
        raise HTTPException(status_code=503, detail="Synology storage data unavailable")
    return StorageResponse(
        bays=[BayResponse(label=b.label, status=b.status) for b in state.bays],
        available=state.available,
        used=state.used,
        reserved=state.reserved,
    )
