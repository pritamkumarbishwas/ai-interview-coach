from datetime import datetime

from pydantic import BaseModel, Field


class DashboardInterview(BaseModel):
    """A recent interview; `score` is the report score once completed."""

    id: str
    role: str
    type: str
    difficulty: str
    status: str
    target_questions: int
    answered_count: int
    score: float | None = None
    created_at: datetime


class DashboardStats(BaseModel):
    interviews_total: int
    interviews_completed: int
    interviews_in_progress: int
    questions_answered: int
    # None until at least one interview has a cached report.
    average_score: float | None = None
    strong_topics: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    recent: list[DashboardInterview] = Field(default_factory=list)
