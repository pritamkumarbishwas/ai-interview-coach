"""Data-subject access (GDPR Art. 15) export.

The counterpart to erasure: a recruiter can export everything the platform holds
about one screening candidate as a machine-readable JSON document. Internal
secrets (the magic-link `token_hash`, the guest identity) are never included.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class InvitationData(BaseModel):
    id: str
    job_id: str
    template_id: str | None = None
    candidate_name: str
    candidate_email: str
    role: str
    company: str
    interview_type: str
    difficulty: str
    target_questions: int
    proctoring_mode: str
    round_minutes: int
    rubric: list[str] = Field(default_factory=list)
    pass_threshold: float
    status: str
    decision: str
    decision_note: str
    expires_at: datetime | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    erased_at: datetime | None = None


class RecordingData(BaseModel):
    kind: str
    file_id: str
    content_type: str
    size_bytes: int
    chunk_count: int
    finalized: bool
    created_at: datetime | None = None


class InterviewData(BaseModel):
    """The candidate's session data (raw subtrees, already JSON-safe)."""

    id: str
    status: str
    type: str
    difficulty: str
    proctoring_mode: str
    rubric: list[str] = Field(default_factory=list)
    pass_threshold: float
    target_questions: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    questions: list[dict] = Field(default_factory=list)
    answers: list[dict] = Field(default_factory=list)
    report: dict | None = None
    proctoring_session: dict | None = None


class CandidateDataExport(BaseModel):
    """Everything stored about one candidate, for a right-of-access request."""

    generated_at: datetime
    invitation: InvitationData
    interview: InterviewData | None = None
    recordings: list[RecordingData] = Field(default_factory=list)
