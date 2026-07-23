from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/api/health",
    summary="Health check",
    description="No auth required — used to confirm the backend is reachable.",
)
async def health() -> dict[str, str]:
    """Trivial liveness check.

    Returns:
        `{"status": "ok"}`, always — this endpoint has no dependencies to fail.
    """
    return {"status": "ok"}
