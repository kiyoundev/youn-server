from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

AnalystType = Literal["market", "social", "news", "fundamentals"]


class StockAlertCreate(BaseModel):
    ticker: str
    target_price: float
    direction: Literal["above", "below"]
    run_analysis: bool = False
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    anthropic_effort: Literal["high", "medium", "low"] | None = None
    max_debate_rounds: int | None = None
    max_risk_discuss_rounds: int | None = None
    analysts: list[AnalystType] | None = None


class StockAlertUpdate(BaseModel):
    target_price: float | None = None
    direction: Literal["above", "below"] | None = None
    active: bool | None = None
    run_analysis: bool | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    anthropic_effort: Literal["high", "medium", "low"] | None = None
    max_debate_rounds: int | None = None
    max_risk_discuss_rounds: int | None = None
    analysts: list[AnalystType] | None = None


class StockAlertResponse(BaseModel):
    id: int
    ticker: str
    target_price: float
    direction: str
    last_price: float | None
    alerted_at: datetime | None
    active: bool
    run_analysis: bool
    deep_think_llm: str | None
    quick_think_llm: str | None
    anthropic_effort: str | None
    max_debate_rounds: int | None
    max_risk_discuss_rounds: int | None
    analysts: list[AnalystType] | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("analysts", mode="before")
    @classmethod
    def _csv_to_list(cls, v: object) -> object:
        if isinstance(v, str):
            return v.split(",") if v else None
        return v
