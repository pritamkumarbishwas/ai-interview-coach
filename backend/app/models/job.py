"""A job requisition: an open role a company is hiring for.

Distinct from two similarly named concepts:

- ``app.models.job_description.JobDescription`` — a pasted posting used to
  ground a candidate's practice interview.
- ``app.core.jobs.Job`` — an internal background-queue task.

A requisition is the company-facing object a recruiter attaches an
``InterviewTemplate`` to and then invites candidates against.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["draft", "open", "closed"]


class Job(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    user_id: str
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    status: JobStatus = "draft"
    # The interview template candidates are screened with; optional until the
    # recruiter picks one.
    template_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
