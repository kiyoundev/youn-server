from datetime import datetime

from pydantic import BaseModel


class PriceHistoryResponse(BaseModel):
    id: int
    watch_item_id: int
    price: float
    checked_at: datetime

    model_config = {"from_attributes": True}
