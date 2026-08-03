from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.listing import ListingResponse


class ProductCreate(BaseModel):
    name: str
    target_price: float
    url: str
    retailer: str | None = None
    scraper_type: Literal["patchright"] | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None


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
