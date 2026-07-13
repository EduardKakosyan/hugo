from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fact:
    id: int
    content: str
    created_at: datetime
