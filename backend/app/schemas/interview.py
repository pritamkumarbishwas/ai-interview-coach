from datetime import datetime

from pydantic import BaseModel, Field

from app.models.interview import Difficulty, InterviewStatus, InterviewType, Level


class InterviewCreate(BaseModel):
    resume_id: str
    jd_id: str
    role: str = Field(min_length=1, max_length=200)
    level: Level = "mid"
    type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"


class QuestionOut(BaseModel):
    id: str
    sequence: int
    text: str


class InterviewSummary(BaseModel):
    """List projection — the question texts stay out of the list response."""

    id: str
    role: str
    type: InterviewType
    difficulty: Difficulty
    status: InterviewStatus
    question_count: int = 0
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
    questions: list[QuestionOut] = []
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
