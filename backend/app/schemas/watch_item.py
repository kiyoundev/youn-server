from datetime import datetime

from pydantic import BaseModel


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
