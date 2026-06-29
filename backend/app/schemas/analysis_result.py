from datetime import datetime

from pydantic import BaseModel


class AnalysisResultResponse(BaseModel):
    id: int
    stock_alert_id: int
    event_id: int | None
    ticker: str
    triggered_price: float
    result: dict | None
    status: str
    action: str | None
    price_target: float | None
    stop_loss: float | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
