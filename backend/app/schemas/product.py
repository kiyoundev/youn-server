from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.listing import ListingResponse
from app.schemas.validators import strip_whitespace, validate_http_url


class ProductCreate(BaseModel):
    name: str
    target_price: float
    # Zero or more listing URLs, created in the same request as the product
    # (bulk, not chained) — auto-detect only, no per-URL retailer/scraper_type
    # override here (those live on ListingCreate, where they're meaningful
    # against exactly one URL; a single override field doesn't make sense
    # once this is a list). A product with urls=[] gets created with zero
    # listings — same accepted state as before, just no longer the *only*
    # way to reach a listingless product.
    urls: list[str] = []

    _strip_name = field_validator("name")(strip_whitespace)

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, value: list[str]) -> list[str]:
        for url in value:
            validate_http_url(url)
        return value


class ProductUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None

    _strip_name = field_validator("name")(strip_whitespace)


class ProductResponse(BaseModel):
    id: int
    name: str
    target_price: float
    alerted_at: datetime | None
    status: Literal["watching", "triggered", "paused", "failed"]
    last_checked: datetime | None
    listings: list[ListingResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingFailure(BaseModel):
    url: str
    detail: str


class ProductCreateResponse(BaseModel):
    """POST /api/items's actual response shape — product plus whichever of
    the requested URLs didn't make it in (duplicate, in-batch collision, or
    unscrapable), so a partial success is fully representable in one
    response instead of silently dropping which URLs failed and why."""

    product: ProductResponse
    failed: list[ListingFailure] = []
