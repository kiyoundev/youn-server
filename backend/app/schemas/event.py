from datetime import datetime

from pydantic import BaseModel


class EventResponse(BaseModel):
    id: int
    type: str
    payload: dict
    status: str
    created_at: datetime
    processed_at: datetime | None

    model_config = {"from_attributes": True}
