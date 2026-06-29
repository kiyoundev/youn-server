from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScraperResult:
    price: float | None
    status: Literal["ok", "oos", "error"]
