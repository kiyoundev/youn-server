from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StockAlertCreate(BaseModel):
    ticker: str
    target_price: float
    direction: Literal["above", "below"]
    run_analysis: bool = False


class StockAlertUpdate(BaseModel):
    target_price: float | None = None
    direction: Literal["above", "below"] | None = None
    active: bool | None = None
    run_analysis: bool | None = None


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
