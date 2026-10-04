from datetime import UTC, datetime

from pydantic import BaseModel, Field


class PreparationStep(BaseModel):
    focus: str = Field(min_length=1)
    actions: list[str] = Field(min_length=1)


class Report(BaseModel):
    """Final interview report, cached on the interview document.

    Every number and topic list here is aggregated in code from the stored
    evaluations; the LLM only writes `narrative` and `preparation_plan`.
    """

    overall_score: float
    technical_score: float
    communication_score: float
    strong_topics: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    topics_to_study: list[str] = Field(default_factory=list)
    narrative: str
    preparation_plan: list[PreparationStep]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
