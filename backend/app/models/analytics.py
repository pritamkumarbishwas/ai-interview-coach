"""Phase 8: job-level recruiting analytics (advisory, aggregate-only).

These models describe a *funnel* and *distribution* view of one requisition's
candidates. Everything here is derived from stored invitations and advisory
scorecards; nothing is scored here and no candidate identity is involved.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime


class ScoreBucket(BaseModel):
    """One band of the advisory score distribution (e.g. "80-89")."""

    label: str
    count: int = 0


class JobAnalytics(BaseModel):
    """Aggregate funnel + score/integrity distribution for a single job."""

    job_id: str
    total_invited: int = 0
    # Invitation status counts (mutually exclusive; "started" = in progress).
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    expired: int = 0
    revoked: int = 0
    # completed / total_invited (0.0 when nobody was invited).
    completion_rate: float = 0.0
    # Advisory pass rate: completed candidates at/above their threshold.
    passed: int = 0
    pass_rate: float = 0.0
    average_score: float = 0.0
    median_score: float = 0.0
    score_distribution: list[ScoreBucket] = Field(default_factory=list)
    # Human decisions recorded so far, keyed by decision.
    decisions: dict[str, int] = Field(default_factory=dict)
    # Advisory integrity level counts across completed sessions.
    integrity_distribution: dict[str, int] = Field(default_factory=dict)
    generated_at: ISTDateTime = Field(default_factory=lambda: datetime.now(UTC))
