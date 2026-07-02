from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

AnalystType = Literal["market", "social", "news", "fundamentals"]
AlertType = Literal["buy_signal", "stop_loss", "take_profit"]


def alert_type_direction_mismatch(direction: str, alert_type: str) -> bool:
    """stop_loss only makes sense selling on a drop (direction="below"); take_profit
    only makes sense selling on a rise (direction="above"). Any other pairing would
    fire urgent, confidently-worded notification copy in the wrong direction."""
    return (alert_type == "stop_loss" and direction != "below") or (
        alert_type == "take_profit" and direction != "above"
    )


_MISMATCH_DETAIL = "stop_loss requires direction='below'; take_profit requires direction='above'"


class StockAlertCreate(BaseModel):
    ticker: str
    target_price: float
    direction: Literal["above", "below"]
    alert_type: AlertType = "buy_signal"
    run_analysis: bool = False
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    anthropic_effort: Literal["high", "medium", "low"] | None = None
    max_debate_rounds: int | None = None
    max_risk_discuss_rounds: int | None = None
    analysts: list[AnalystType] | None = None

    @model_validator(mode="after")
    def _check_alert_type_direction(self) -> "StockAlertCreate":
        if alert_type_direction_mismatch(self.direction, self.alert_type):
            raise ValueError(_MISMATCH_DETAIL)
        return self


class StockAlertUpdate(BaseModel):
    target_price: float | None = None
    direction: Literal["above", "below"] | None = None
    alert_type: AlertType | None = None
    active: bool | None = None
    run_analysis: bool | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    anthropic_effort: Literal["high", "medium", "low"] | None = None
    max_debate_rounds: int | None = None
    max_risk_discuss_rounds: int | None = None
    analysts: list[AnalystType] | None = None

    @model_validator(mode="after")
    def _check_alert_type_direction(self) -> "StockAlertUpdate":
        if (
            self.direction is not None
            and self.alert_type is not None
            and alert_type_direction_mismatch(self.direction, self.alert_type)
        ):
            raise ValueError(_MISMATCH_DETAIL)
        return self


class StockAlertResponse(BaseModel):
    id: int
    ticker: str
    target_price: float
    direction: str
    alert_type: str
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
