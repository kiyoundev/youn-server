import secrets

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    if not settings.api_key or x_api_key is None or not secrets.compare_digest(
        x_api_key, settings.api_key
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
