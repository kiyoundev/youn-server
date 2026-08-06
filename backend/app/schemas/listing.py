from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.validators import validate_http_url


class ListingCreate(BaseModel):
    url: str
    retailer: str | None = None
    scraper_type: Literal["patchright"] | None = None

    _validate_url = field_validator("url")(validate_http_url)


class ListingUpdate(BaseModel):
    active: bool | None = None


class ListingResponse(BaseModel):
    id: int
    retailer: str
    url: str
    last_price: float | None
    last_scrape_status: Literal["ok", "oos", "error"] | None
    active: bool
    last_checked: datetime | None
    product_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
