import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

# Declaring the header as a security scheme is what gives Swagger UI its
# Authorize button. auto_error=False keeps the 401 below as the only one, so a
# missing key and a wrong key still return the same "Invalid API key".
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    if not settings.api_key or api_key is None or not secrets.compare_digest(
        api_key, settings.api_key
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
