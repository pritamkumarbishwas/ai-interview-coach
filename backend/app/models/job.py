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
# Outbound ATS integration flavour; "generic" is a plain JSON envelope.
WebhookProvider = Literal["generic", "greenhouse", "lever"]


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
    # --- Outbound ATS webhook (Phase 8) ------------------------------------
    # When enabled, a signed `candidate.decided` event is POSTed here whenever a
    # recruiter records a decision. The secret signs every request and is never
    # returned by the API.
    webhook_url: str = ""
    webhook_provider: WebhookProvider = "generic"
    webhook_secret: str = ""
    webhook_enabled: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
