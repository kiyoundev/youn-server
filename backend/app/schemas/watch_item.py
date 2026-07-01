from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WatchItemCreate(BaseModel):
    name: str
    url: str
    target_price: float
    scraper_type: Literal["patchright"] | None = None


class WatchItemUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = None
    active: bool | None = None


class WatchItemResponse(BaseModel):
    id: int
    name: str
    url: str
    retailer: str
    target_price: float
    last_price: float | None
    alerted_at: datetime | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
