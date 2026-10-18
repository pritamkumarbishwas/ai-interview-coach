from pydantic import BaseModel, Field, field_validator

from app.core.timeutil import ISTDateTime
from app.models.job import JobStatus, WebhookProvider


def _validate_webhook_url(value: str | None) -> str | None:
    if not value:
        return value
    url = value.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("webhook_url must be an http(s) URL")
    return url


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
    # Outbound ATS webhook config. Sending `webhook_secret: ""` clears it.
    webhook_url: str | None = Field(default=None, max_length=500)
    webhook_provider: WebhookProvider | None = None
    webhook_secret: str | None = Field(default=None, max_length=200)
    webhook_enabled: bool | None = None

    _check_webhook_url = field_validator("webhook_url")(_validate_webhook_url)


class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    status: JobStatus
    template_id: str | None = None
    # Staff assigned to review this requisition (read/decide access).
    reviewer_ids: list[str] = Field(default_factory=list)
    # The requisition's owner. Surfaced so an admin's cross-owner list/detail
    # can show who created it.
    owner_id: str | None = None
    webhook_url: str = ""
    webhook_provider: WebhookProvider = "generic"
    webhook_enabled: bool = False
    # Whether a signing secret is stored; the secret itself is never returned.
    webhook_configured: bool = False
    created_at: ISTDateTime
    updated_at: ISTDateTime


class JobSummary(BaseModel):
    """List projection — the description text stays out of the list response."""

    id: str
    title: str
    company: str
    status: JobStatus
    template_id: str | None = None
    reviewer_ids: list[str] = Field(default_factory=list)
    owner_id: str | None = None
    created_at: ISTDateTime


class ReviewerAssignment(BaseModel):
    """Replace the reviewer list on a requisition."""

    reviewer_ids: list[str] = Field(default_factory=list)
