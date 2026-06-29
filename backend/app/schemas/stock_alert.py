from datetime import datetime

from pydantic import BaseModel


class StockAlertResponse(BaseModel):
    id: int
    ticker: str
    target_price: float
    direction: str
    last_price: float | None
    alerted_at: datetime | None
    active: bool
    run_analysis: bool
    created_at: datetime

    model_config = {"from_attributes": True}
