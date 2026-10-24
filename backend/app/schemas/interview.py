from typing import Literal

from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime
from app.models.answer import Answer
from app.models.interview import (
    Difficulty,
    InterviewKind,
    InterviewStatus,
    InterviewType,
    Level,
    ProctoringMode,
    ProctoringSession,
    RecordingMeta,
)

DEFAULT_TARGET_QUESTIONS = 5


class InterviewCreate(BaseModel):
    resume_id: str | None = None
    jd_id: str
    role: str = Field(min_length=1, max_length=200)
    level: Level = "mid"
    type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"
    proctoring_mode: ProctoringMode = "strict"
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
    kind: InterviewKind = "practice"
    type: InterviewType
    difficulty: Difficulty
    status: InterviewStatus
    proctoring_mode: ProctoringMode = "strict"
    question_count: int = 0
    answered_count: int = 0
    target_questions: int = DEFAULT_TARGET_QUESTIONS
    score: float | None = None
    created_at: ISTDateTime
    completed_at: ISTDateTime | None = None


class InterviewListOut(BaseModel):
    """Paginated list response; `total` is the count before pagination."""

    items: list[InterviewSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 24
    offset: int = 0
    has_more: bool = False


ResultsSort = Literal["recent", "score_desc", "score_asc"]


class InterviewResultsOut(BaseModel):
    items: list[InterviewSummary] = Field(default_factory=list)
    total: int = 0
    scored_count: int = 0
    average_score: float | None = None
    best_score: float | None = None


class RecordingPlaybackOut(BaseModel):
    path: str
    expires_at: ISTDateTime
    expires_in: int


class InterviewOut(BaseModel):
    id: str
    resume_id: str
    jd_id: str
    role: str
    kind: InterviewKind = "practice"
    level: Level
    type: InterviewType
    difficulty: Difficulty
    status: InterviewStatus
    proctoring_mode: ProctoringMode = "strict"
    proctoring_session: ProctoringSession | None = None
    target_questions: int = DEFAULT_TARGET_QUESTIONS
    questions: list[QuestionOut] = []
    answers: list[Answer] = []
    # Recording metadata by kind (bytes are in GridFS, never inline here).
    recordings: dict[str, RecordingMeta] = {}
    # Whether this deployment has server-side speech-to-text configured. The
    # frontend only offers the fallback mic path when this is true.
    transcription_enabled: bool = False
    current_question_id: str | None = None
    created_at: ISTDateTime
    started_at: ISTDateTime | None = None
    completed_at: ISTDateTime | None = None


class ProctoringConsent(BaseModel):
    consent: bool


class ProctoringEventCreate(BaseModel):
    type: str
    details: dict = {}


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
