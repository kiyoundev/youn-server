from pydantic import BaseModel


class MarketHistoryPoint(BaseModel):
    date: str
    close: float
