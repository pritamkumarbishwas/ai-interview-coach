"""Review workspace read models: a transcript ↔ recording timeline.

A timeline interleaves the candidate's answers with the advisory integrity
moments, each stamped with a position (in seconds) inside the session
recording, so a reviewer can jump straight to the moment. Positions are
advisory navigation aids, never scoring inputs.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

TimelineEntryKind = Literal["answer", "signal"]


class TimelineEntry(BaseModel):
    kind: TimelineEntryKind
    # Seconds from the start of the recording (media time 0).
    at_seconds: float = 0.0
    at: datetime | None = None
    label: str = ""
    # Answer entries.
    question_id: str = ""
    question: str = ""
    answer: str = ""
    competency: str = ""
    score: int | None = None
    # Signal entries.
    severity: int = 0


class ReviewTimeline(BaseModel):
    interview_id: str
    # True when offsets are anchored to the client-reported recorder start
    # (accurate); False means they are anchored to the session start (approximate).
    anchored_to_recording: bool = False
    recording_available: bool = False
    duration_seconds: float = 0.0
    entries: list[TimelineEntry] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
