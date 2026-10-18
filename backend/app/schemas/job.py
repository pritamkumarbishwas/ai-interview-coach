from datetime import datetime

from pydantic import BaseModel, Field

from app.models.job import JobStatus


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=100_000)
    status: JobStatus = "draft"
    template_id: str | None = None


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)
    status: JobStatus | None = None
    # `null` detaches the template; omitting the field leaves it unchanged.
    template_id: str | None = None


class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    status: JobStatus
    template_id: str | None = None
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    """List projection — the description text stays out of the list response."""

    id: str
    title: str
    company: str
    status: JobStatus
    template_id: str | None = None
    created_at: datetime
