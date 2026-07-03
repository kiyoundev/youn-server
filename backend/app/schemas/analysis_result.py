from datetime import datetime

from pydantic import BaseModel


class AnalysisResultResponse(BaseModel):
    id: int
    stock_alert_id: int
    event_id: int | None
    ticker: str
    triggered_price: float | None
    result: dict | None
    status: str
    action: str | None
    price_target: float | None
    report_path: str | None
    llm_calls: int
    tokens_in: int
    tokens_out: int
    tool_calls: int
    last_heartbeat_at: datetime | None
    error_reason: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
