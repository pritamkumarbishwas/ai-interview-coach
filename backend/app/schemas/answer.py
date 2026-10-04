from pydantic import BaseModel, Field

from app.models.answer import Evaluation, NextStep, ScoreBreakdown
from app.models.interview import InterviewStatus
from app.schemas.interview import QuestionOut


class AnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=20_000)


class AnswerResultOut(BaseModel):
    """The evaluation of the submitted answer plus the next question (if any)."""

    question_id: str
    status: InterviewStatus
    evaluation: Evaluation
    next_question: QuestionOut | None = None
    questions_answered: int
    target_questions: int


class EvaluationGeneration(BaseModel):
    """LLM output shape for answer evaluation (the service adds `overall`)."""

    scores: ScoreBreakdown
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    feedback: str = Field(min_length=1)
    improved_answer: str = Field(min_length=1)
    next_step: NextStep = "new_topic"
