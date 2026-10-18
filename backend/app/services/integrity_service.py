"""Integrity aggregation: turn passive proctoring events into an advisory report.

Design rules (see the plan's risk table):
- Advisory only. The output informs a human; it never blocks or auto-rejects.
- Deterministic. Scores come from fixed weights in code, not an LLM, so the
  same session always yields the same number.
- Low noise. Benign/positive events (focus regained, devices back on) are
  ignored; only risk-bearing signals count against the score.
"""

import logging
from datetime import datetime

from app.models.integrity import (
    IntegrityLevel,
    IntegrityMoment,
    IntegrityReport,
    IntegritySignalCount,
)
from app.models.interview import Interview

logger = logging.getLogger(__name__)

# event type -> (human label, risk weight). Events not listed here (including
# all the "recovered" variants) are neutral and never lower the score.
SIGNAL_WEIGHTS: dict[str, tuple[str, int]] = {
    "tab_blur": ("Switched away from the interview tab", 6),
    "window_blur": ("Interview window lost focus", 3),
    "camera_off": ("Camera turned off", 8),
    "screen_off": ("Screen share stopped", 6),
    "mic_off": ("Microphone muted", 3),
    "copy": ("Copied content from the page", 2),
    "paste": ("Pasted content into an answer", 4),
    "fullscreen_exit": ("Left fullscreen", 1),
}

# A moment is "flagged" (appears on the timeline) at or above this weight.
FLAG_THRESHOLD = 3

LEVEL_BANDS: tuple[tuple[int, IntegrityLevel], ...] = (
    (90, "low"),
    (75, "moderate"),
    (55, "elevated"),
)


def _level_for(score: int) -> IntegrityLevel:
    for floor, level in LEVEL_BANDS:
        if score >= floor:
            return level
    return "high"


class IntegrityService:
    """Builds the advisory integrity report from a stored interview."""

    def build(self, interview: Interview) -> IntegrityReport:
        session = interview.proctoring_session
        events = list(session.events) if session else []

        counts: dict[str, int] = {}
        moments: list[IntegrityMoment] = []
        penalty = 0
        for event in events:
            spec = SIGNAL_WEIGHTS.get(event.type)
            if spec is None:
                continue
            label, weight = spec
            counts[event.type] = counts.get(event.type, 0) + 1
            penalty += weight
            if weight >= FLAG_THRESHOLD:
                moments.append(
                    IntegrityMoment(
                        at=event.timestamp,
                        type=event.type,
                        label=label,
                        severity=weight,
                        details=event.details,
                    )
                )

        score = max(0, min(100, 100 - penalty))
        level = _level_for(score)

        signals = [
            IntegritySignalCount(
                type=signal_type,
                label=SIGNAL_WEIGHTS[signal_type][0],
                count=count,
                weight=SIGNAL_WEIGHTS[signal_type][1],
            )
            for signal_type, count in sorted(
                counts.items(), key=lambda item: (-SIGNAL_WEIGHTS[item[0]][1], item[0])
            )
        ]
        # Most recent (and most severe) moments first for quick triage.
        moments.sort(key=lambda moment: moment.at or datetime.min, reverse=True)

        recording = interview.recordings.get("camera")
        notes: list[str] = []
        if not events and interview.proctoring_mode != "off":
            notes.append("No integrity signals were observed during the session.")
        if interview.proctoring_mode == "off":
            notes.append("Proctoring was disabled for this interview.")
        if recording is not None and not recording.finalized:
            notes.append("The session recording was not finalized.")

        return IntegrityReport(
            interview_id=interview.id or "",
            advisory=True,
            score=score,
            level=level,
            session_started_at=session.started_at if session else None,
            session_ended_at=session.ended_at if session else None,
            recording_available=bool(recording and recording.finalized),
            recording_size_bytes=recording.size_bytes if recording else 0,
            signals=signals,
            moments=moments,
            notes=notes,
        )


integrity_service = IntegrityService()
