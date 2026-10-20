from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime
from app.models.interview import (
    Difficulty,
    InterviewKind,
    InterviewStatus,
    InterviewType,
)

DEFAULT_TARGET_QUESTIONS = 5


class DashboardInterview(BaseModel):
    """A recent interview; `score` is the report score once completed."""

    id: str
    role: str
    kind: InterviewKind = "practice"
    type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"
    status: InterviewStatus = "created"
    target_questions: int = DEFAULT_TARGET_QUESTIONS
    answered_count: int = 0
    score: float | None = None
    created_at: ISTDateTime


class DashboardActiveInterview(BaseModel):
    """The newest unfinished interview, used for the resume CTA."""

    id: str
    role: str
    status: InterviewStatus
    created_at: ISTDateTime


class TopicCount(BaseModel):
    topic: str
    count: int


class DashboardStats(BaseModel):
    interviews_total: int
    interviews_completed: int
    interviews_in_progress: int
    interviews_not_started: int = 0
    questions_answered: int
    scored_count: int = 0
    # None until at least one interview has a cached report.
    average_score: float | None = None
    strong_topics: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    strong_topic_counts: list[TopicCount] = Field(default_factory=list)
    weak_topic_counts: list[TopicCount] = Field(default_factory=list)
    active_interview: DashboardActiveInterview | None = None
    recent: list[DashboardInterview] = Field(default_factory=list)
