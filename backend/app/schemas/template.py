from datetime import datetime

from pydantic import BaseModel, Field

from app.models.interview import Difficulty, InterviewType, ProctoringMode
from app.models.template_config import InterviewTemplateConfig


class BankQuestionInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    topic: str = Field(default="", max_length=200)
    competency: str = Field(default="", max_length=200)
    interview_type: InterviewType | None = None
    difficulty: Difficulty | None = None


class BankQuestionOut(BankQuestionInput):
    id: str


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    config: InterviewTemplateConfig = Field(default_factory=InterviewTemplateConfig)
    question_bank: list[BankQuestionInput] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    config: InterviewTemplateConfig | None = None
    # `null` clears the bank; a list replaces it wholesale.
    question_bank: list[BankQuestionInput] | None = None


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    config: InterviewTemplateConfig
    question_bank: list[BankQuestionOut]
    created_at: datetime
    updated_at: datetime


class TemplateSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    proctoring_mode: ProctoringMode = "strict"
    round_count: int = 0
    question_count: int = 0
    created_at: datetime


class TemplatePreviewRequest(BaseModel):
    """Optional overrides for a one-off preview question generated inline."""

    role: str = Field(default="", max_length=200)
    round_key: str | None = None
    interview_type: InterviewType | None = None
    difficulty: Difficulty | None = None
    topic: str = Field(default="", max_length=200)


class TemplatePreviewOut(BaseModel):
    question: str
    topic: str = ""
    interview_type: InterviewType
    difficulty: Difficulty
