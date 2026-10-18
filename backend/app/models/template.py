"""A reusable interview template: rounds, integrity policy, and a question bank."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.interview import Difficulty, InterviewType
from app.models.template_config import InterviewTemplateConfig


class BankQuestion(BaseModel):
    """One curated question a template can draw on (optionally round-tagged)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    text: str = Field(min_length=1, max_length=2000)
    topic: str = ""
    competency: str = ""
    # When set, the question belongs to rounds of this type; when unset the
    # builder may offer it for any round.
    interview_type: InterviewType | None = None
    difficulty: Difficulty | None = None


class InterviewTemplate(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    user_id: str
    name: str
    description: str = ""
    config: InterviewTemplateConfig = Field(default_factory=InterviewTemplateConfig)
    question_bank: list[BankQuestion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
