from typing import Literal

from pydantic import BaseModel

BayStatus = Literal["empty", "healthy", "warning", "error"]


class BayResponse(BaseModel):
    label: str
    status: BayStatus


class StorageResponse(BaseModel):
    bays: list[BayResponse]
    available: float
    used: float
    reserved: float
