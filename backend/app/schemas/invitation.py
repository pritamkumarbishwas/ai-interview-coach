from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.interview import Difficulty, InterviewType, ProctoringMode
from app.models.invitation import Decision, InvitationStatus


class InvitationCreate(BaseModel):
    job_id: str = Field(min_length=1)
    candidate_name: str = Field(default="", max_length=120)
    candidate_email: EmailStr
    # Which round of the job's template this invitation is for (defaults to the
    # template's first round).
    round_key: str | None = None
    # Optional scheduling window (server-enforced).
    start_window_start: datetime | None = None
    start_window_end: datetime | None = None
    # Overrides the configured default link lifetime (1-30 days).
    expires_in_days: int | None = Field(default=None, ge=1, le=30)
    # Extra time added to the round (accessibility accommodation), in minutes.
    extra_minutes: int = Field(default=0, ge=0, le=180)


class InvitationExtend(BaseModel):
    """Grant extra time on an already-started (or pending) invitation."""

    minutes: int = Field(ge=1, le=180)


class InvitationDecision(BaseModel):
    """Record a human decision after reviewing the advisory scorecard."""

    decision: Decision
    note: str = Field(default="", max_length=1_000)


class InvitationOut(BaseModel):
    id: str
    job_id: str
    candidate_name: str = ""
    candidate_email: EmailStr
    role: str
    status: InvitationStatus
    expires_at: datetime
    round_minutes: int = 30
    round_deadline: datetime | None = None
    interview_id: str | None = None
    decision: Decision = "pending"
    decision_note: str = ""
    decided_at: datetime | None = None
    created_at: datetime
    # Returned to the recruiter so the link can be shared if email is not
    # configured; never derivable from the stored record.
    accept_url: str | None = None


class ShortlistEntry(BaseModel):
    """One candidate in the job's ranked shortlist.

    Every scored field is advisory; `needs_review` is true until a human
    records a decision.
    """

    invitation_id: str
    candidate_name: str = ""
    candidate_email: EmailStr
    status: InvitationStatus
    decision: Decision = "pending"
    overall_score: float = 0.0
    threshold: float = 0.0
    meets_threshold: bool = False
    competency_count: int = 0
    integrity_level: str | None = None
    integrity_score: int | None = None
    generated_at: datetime | None = None


class InvitationSessionOut(BaseModel):
    """Pre-check payload for the candidate (no account, no scores)."""

    status: InvitationStatus
    role: str
    company: str = ""
    interview_type: InterviewType
    difficulty: Difficulty
    proctoring_mode: ProctoringMode
    consent_required: bool
    # Total number of questions the candidate will be asked (progress display).
    total_questions: int = 5
    started: bool
    expires_at: datetime
    start_window_start: datetime | None = None
    start_window_end: datetime | None = None
    round_deadline: datetime | None = None


class StartInterviewRequest(BaseModel):
    # Proctored interviews require explicit consent before the first question.
    consent: bool = False
