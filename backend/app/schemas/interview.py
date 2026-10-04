from datetime import datetime

from pydantic import BaseModel, Field

from app.models.answer import Answer
from app.models.interview import Difficulty, InterviewStatus, InterviewType, Level

DEFAULT_TARGET_QUESTIONS = 5


class InterviewCreate(BaseModel):
    resume_id: str
    jd_id: str
    role: str = Field(min_length=1, max_length=200)
    level: Level = "mid"
    type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"
    target_questions: int = Field(default=DEFAULT_TARGET_QUESTIONS, ge=1, le=20)


class QuestionOut(BaseModel):
    id: str
    sequence: int
    text: str
    topic: str = ""


class InterviewSummary(BaseModel):
    """List projection — the question texts stay out of the list response."""

    id: str
    role: str
    type: InterviewType
    difficulty: Difficulty
    status: InterviewStatus
    question_count: int = 0
    answered_count: int = 0
    target_questions: int = DEFAULT_TARGET_QUESTIONS
    created_at: datetime


class InterviewOut(BaseModel):
    id: str
    resume_id: str
    jd_id: str
    role: str
    level: Level
    type: InterviewType
    difficulty: Difficulty
    status: InterviewStatus
    target_questions: int = DEFAULT_TARGET_QUESTIONS
    questions: list[QuestionOut] = []
    answers: list[Answer] = []
    current_question_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class CurrentQuestionOut(BaseModel):
    interview_id: str
    status: InterviewStatus
    question: QuestionOut
    question_number: int
    total_asked: int


class QuestionGeneration(BaseModel):
    """LLM output shape for question generation."""

    question: str = Field(min_length=1, description="A single interview question to ask next")
    topic: str = Field(
        default="",
        description="Short topic label for this question (used to avoid repeats)",
    )
