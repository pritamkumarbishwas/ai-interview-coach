from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

# How the evaluator wants the interview to proceed after this answer.
NextStep = Literal["follow_up", "harder", "easier", "new_topic"]


class ScoreBreakdown(BaseModel):
    """Five 0-100 scores (matches the frontend's metric labels)."""

    technical: int = Field(ge=0, le=100)
    relevance: int = Field(ge=0, le=100)
    completeness: int = Field(ge=0, le=100)
    structure: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)

    @property
    def overall(self) -> int:
        values = (
            self.technical,
            self.relevance,
            self.completeness,
            self.structure,
            self.clarity,
        )
        return round(sum(values) / len(values))


class Evaluation(BaseModel):
    scores: ScoreBreakdown
    overall: int = Field(default=0, ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    feedback: str = ""
    improved_answer: str = ""
    next_step: NextStep = "new_topic"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Answer(BaseModel):
    id: str
    question_id: str
    text: str
    evaluation: Evaluation
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
