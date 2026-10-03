from datetime import datetime

from pydantic import BaseModel, Field


class JobDescriptionStructuredData(BaseModel):
    role_title: str = Field(description="The title of the position")
    required_skills: list[str] = Field(description="A list of required technical and soft skills")
    responsibilities: list[str] = Field(description="A list of key responsibilities for the role")


class JobDescriptionInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    raw_text: str = Field(min_length=1, max_length=100_000)


class JobDescriptionResponse(BaseModel):
    id: str
    title: str
    company: str
    structured_data: JobDescriptionStructuredData


class JobDescriptionSummary(BaseModel):
    """List projection — a short snippet instead of the full posting text."""

    id: str
    title: str
    company: str
    snippet: str = ""
    created_at: datetime
