from datetime import datetime

from pydantic import BaseModel, Field

from app.models.report import PreparationStep


class ReportGeneration(BaseModel):
    """LLM output shape for the narrative part of the report.

    The score fields are computed in code, never taken from the model.
    """

    narrative: str = Field(min_length=1)
    preparation_plan: list[PreparationStep] = Field(min_length=1)


class ReportOut(BaseModel):
    interview_id: str
    overall_score: float
    technical_score: float
    communication_score: float
    strong_topics: list[str]
    weak_topics: list[str]
    topics_to_study: list[str]
    narrative: str
    preparation_plan: list[PreparationStep]
    generated_at: datetime
