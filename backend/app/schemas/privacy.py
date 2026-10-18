"""Data-subject access (GDPR Art. 15) export.

The counterpart to erasure: a recruiter can export everything the platform holds
about one screening candidate as a machine-readable JSON document. Internal
secrets (the magic-link `token_hash`, the guest identity) are never included.
"""

from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime


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
    expires_at: ISTDateTime | None = None
    created_at: ISTDateTime | None = None
    started_at: ISTDateTime | None = None
    completed_at: ISTDateTime | None = None
    erased_at: ISTDateTime | None = None


class RecordingData(BaseModel):
    kind: str
    file_id: str
    content_type: str
    size_bytes: int
    chunk_count: int
    finalized: bool
    created_at: ISTDateTime | None = None


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
    created_at: ISTDateTime | None = None
    started_at: ISTDateTime | None = None
    completed_at: ISTDateTime | None = None
    questions: list[dict] = Field(default_factory=list)
    answers: list[dict] = Field(default_factory=list)
    report: dict | None = None
    proctoring_session: dict | None = None


class CandidateDataExport(BaseModel):
    """Everything stored about one candidate, for a right-of-access request."""

    generated_at: ISTDateTime
    invitation: InvitationData
    interview: InterviewData | None = None
    recordings: list[RecordingData] = Field(default_factory=list)
