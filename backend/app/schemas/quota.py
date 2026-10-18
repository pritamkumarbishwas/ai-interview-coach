from datetime import datetime

from pydantic import BaseModel, Field


class QuotaStatus(BaseModel):
    action: str
    # None means unlimited.
    limit: int | None = None
    used: int = 0
    remaining: int | None = None


class QuotaSummary(BaseModel):
    role: str
    window_start: datetime
    quotas: list[QuotaStatus] = Field(default_factory=list)
