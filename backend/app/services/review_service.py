"""Builds a review timeline: answers and integrity moments anchored to recording time.

Every offset is computed in code from stored timestamps, so the timeline is
reproducible. Offsets are advisory navigation aids for the reviewer, never
inputs to scoring.
"""

import logging
from datetime import UTC, datetime

from app.models.integrity import IntegrityReport
from app.models.interview import Interview
from app.models.review import ReviewTimeline, TimelineEntry

logger = logging.getLogger(__name__)

RECORDING_KIND = "camera"
MAX_ENTRIES = 500


def _naive(value: datetime) -> datetime:
    """MongoDB hands back naive UTC datetimes; normalize before subtracting."""
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


class ReviewService:
    def build(self, interview: Interview, integrity: IntegrityReport) -> ReviewTimeline:
        recording = interview.recordings.get(RECORDING_KIND)
        recording_available = bool(recording and recording.finalized)

        base = self._anchor(interview, recording.capture_started_at if recording else None)
        anchored_to_recording = bool(recording and recording.capture_started_at is not None)

        entries: list[TimelineEntry] = []
        if base is not None:
            questions = {question.id: question for question in interview.questions}
            for answer in interview.answers:
                question = questions.get(answer.question_id)
                evaluation = answer.evaluation
                entries.append(
                    TimelineEntry(
                        kind="answer",
                        at_seconds=self._offset(answer.created_at, base),
                        at=answer.created_at,
                        label=(question.text if question else "")[:200],
                        question_id=answer.question_id,
                        question=question.text if question else "",
                        answer=answer.text,
                        competency=evaluation.competency if evaluation else "",
                        score=evaluation.overall if evaluation else None,
                    )
                )
            for moment in integrity.moments:
                if moment.at is None:
                    continue
                entries.append(
                    TimelineEntry(
                        kind="signal",
                        at_seconds=self._offset(moment.at, base),
                        at=moment.at,
                        label=moment.label,
                        severity=moment.severity,
                    )
                )

        entries.sort(key=lambda entry: entry.at_seconds)
        entries = entries[:MAX_ENTRIES]
        duration = max((entry.at_seconds for entry in entries), default=0.0)

        return ReviewTimeline(
            interview_id=interview.id or "",
            anchored_to_recording=anchored_to_recording,
            recording_available=recording_available,
            duration_seconds=round(duration, 1),
            entries=entries,
        )

    @staticmethod
    def _anchor(interview: Interview, capture_started_at: datetime | None) -> datetime | None:
        """The wall-clock instant that media time 0 corresponds to.

        Prefer the client-reported recorder start; fall back to the proctoring
        session start, then the interview start, then the first answer, so a
        timeline is still produced for sessions recorded before the client
        reported a start (approximate, and flagged as such).
        """
        session = interview.proctoring_session
        candidates = [
            capture_started_at,
            session.started_at if session else None,
            interview.started_at,
        ]
        for candidate in candidates:
            if candidate is not None:
                return _naive(candidate)
        if interview.answers:
            return _naive(min(answer.created_at for answer in interview.answers))
        return None

    @staticmethod
    def _offset(value: datetime, base: datetime) -> float:
        """Seconds from `base`, clamped at zero (clock skew must not go negative)."""
        return round(max((_naive(value) - base).total_seconds(), 0.0), 1)


review_service = ReviewService()
