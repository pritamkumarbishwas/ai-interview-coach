from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.answer import Answer

InterviewType = Literal["technical", "behavioral", "hr", "mixed", "system_design"]
Difficulty = Literal["beginner", "intermediate", "advanced"]
Level = Literal["junior", "mid", "senior"]
InterviewStatus = Literal["created", "in_progress", "completed"]

# The interview state machine: `start` runs `created -> in_progress`, and
# answering the final question runs `in_progress -> completed`.
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "created": {"in_progress"},
    "in_progress": {"completed"},
    "completed": set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in STATUS_TRANSITIONS.get(current, set())


class Question(BaseModel):
    id: str
    sequence: int
    text: str
    # Topic label (e.g. "database indexing") so later questions can avoid
    # repeats; empty on documents written before topic tracking existed.
    topic: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Interview(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    user_id: str
    resume_id: str
    jd_id: str
    role: str
    level: Level = "mid"
    type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"
    status: InterviewStatus = "created"
    # The interview completes automatically once this many answers are scored.
    target_questions: int = 5
    questions: list[Question] = Field(default_factory=list)
    answers: list[Answer] = Field(default_factory=list)
    current_question_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)

    @property
    def current_question(self) -> Question | None:
        for question in reversed(self.questions):
            if question.id == self.current_question_id:
                return question
        return self.questions[-1] if self.questions else None
