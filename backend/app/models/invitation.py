"""A candidate's magic-link invitation to a screening interview.

Candidates are guests: there is no ``User`` record. Each invitation carries an
internal ``guest_user_id`` (a prefixed id that cannot collide with a real
ObjectId) which owns the screening ``Interview`` and a synthesized job
description, so the existing interview engine runs unchanged.

Only the SHA-256 hash of the token is stored; the raw token travels in the
invitation email. Defaults for the round (type, difficulty, question count,
proctoring) are snapshotted at invite time so a later template edit does not
retroactively change an invitation already sent.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.interview import Difficulty, InterviewType, ProctoringMode

InvitationStatus = Literal["pending", "started", "completed", "expired", "revoked"]


class ScreeningInvitation(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    job_id: str
    template_id: str | None = None
    guest_user_id: str
    # A job description synthesized from the requisition, owned by the guest
    # identity, so question generation has job context without a real posting.
    jd_id: str
    candidate_name: str = ""
    candidate_email: str
    token_hash: str
    role: str
    company: str = ""
    interview_type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"
    target_questions: int = 5
    proctoring_mode: ProctoringMode = "strict"
    round_minutes: int = 30
    status: InvitationStatus = "pending"
    expires_at: datetime
    start_window_start: datetime | None = None
    start_window_end: datetime | None = None
    # Server-authoritative deadline, set when the candidate starts.
    round_deadline: datetime | None = None
    interview_id: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)
