"""Advisory integrity summary for a completed (or in-progress) interview.

Everything here is **advisory**: passive signals are aggregated into a
human-readable timeline and a heuristic confidence score. It is never a
verdict, never auto-rejects, and is always reviewed by a human. The score is
computed deterministically in code (no LLM) from the recorded proctoring
events, so it is stable and auditable.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime

IntegrityLevel = Literal["low", "moderate", "elevated", "high"]


class IntegritySignalCount(BaseModel):
    """How many times one risk-bearing signal was observed."""

    type: str
    label: str
    count: int
    weight: int


class IntegrityMoment(BaseModel):
    """One flagged moment on the timeline (jump-to-moment evidence)."""

    at: ISTDateTime | None = None
    type: str
    label: str
    severity: int
    details: dict = Field(default_factory=dict)


class IntegrityReport(BaseModel):
    interview_id: str
    # Always true today; kept explicit so a UI never presents it as a decision.
    advisory: bool = True
    # 0-100 confidence that the session ran clean; higher is cleaner.
    score: int = Field(ge=0, le=100)
    level: IntegrityLevel
    session_started_at: ISTDateTime | None = None
    session_ended_at: ISTDateTime | None = None
    recording_available: bool = False
    recording_size_bytes: int = 0
    signals: list[IntegritySignalCount] = Field(default_factory=list)
    moments: list[IntegrityMoment] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    generated_at: ISTDateTime = Field(default_factory=lambda: datetime.now(UTC))
