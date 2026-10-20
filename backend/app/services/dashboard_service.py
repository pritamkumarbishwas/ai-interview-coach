"""Dashboard statistics aggregated from the user's interviews and reports."""

import math

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.interview_repository import InterviewRepository
from app.schemas.dashboard import (
    DEFAULT_TARGET_QUESTIONS,
    DashboardActiveInterview,
    DashboardInterview,
    DashboardStats,
    TopicCount,
)

RECENT_LIMIT = 5
# How many of the most frequent strong/weak topics the dashboard shows.
TOPIC_LIMIT = 5
# Read extra topic rows so an overlapping topic can be moved to the stronger
# side without leaving a list short.
TOPIC_SCAN_LIMIT = TOPIC_LIMIT * 2


def _first(rows: list[dict]) -> dict:
    return rows[0] if rows else {}


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _topic_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        topic = row.get("_id")
        if isinstance(topic, str) and topic:
            counts[topic] = int(row.get("count") or 0)
    return counts


def _split_topics(
    strong: dict[str, int],
    weak: dict[str, int],
) -> tuple[list[TopicCount], list[TopicCount]]:
    """Keep a topic on one side only; a tie counts as strong."""
    strong_items: list[TopicCount] = []
    weak_items: list[TopicCount] = []
    for topic in set(strong) | set(weak):
        strong_count = strong.get(topic, 0)
        weak_count = weak.get(topic, 0)
        if strong_count >= weak_count:
            strong_items.append(TopicCount(topic=topic, count=strong_count))
        else:
            weak_items.append(TopicCount(topic=topic, count=weak_count))

    def order(item: TopicCount) -> tuple[int, str]:
        return (-item.count, item.topic)

    strong_items.sort(key=order)
    weak_items.sort(key=order)
    return strong_items[:TOPIC_LIMIT], weak_items[:TOPIC_LIMIT]


class DashboardService:
    def __init__(self, interviews: InterviewRepository) -> None:
        self._interviews = interviews

    async def stats(self, db: AsyncIOMotorDatabase, user_id: str) -> DashboardStats:
        facets = await self._interviews.stats_for_user(
            db,
            user_id,
            recent_limit=RECENT_LIMIT,
            topic_limit=TOPIC_SCAN_LIMIT,
        )

        summary = _first(facets.get("summary") or [])
        scores = _first(facets.get("scores") or [])
        strong_topics, weak_topics = _split_topics(
            _topic_counts(facets.get("strong_topics") or []),
            _topic_counts(facets.get("weak_topics") or []),
        )

        active_rows = facets.get("active") or []
        active_interview = (
            DashboardActiveInterview(
                id=active_rows[0]["_id"],
                role=active_rows[0].get("role") or "",
                status=active_rows[0].get("status") or "created",
                created_at=active_rows[0]["created_at"],
            )
            if active_rows
            else None
        )

        recent = [
            DashboardInterview(
                id=doc["_id"],
                role=doc.get("role") or "",
                kind=doc.get("kind") or "practice",
                type=doc.get("type") or "technical",
                difficulty=doc.get("difficulty") or "intermediate",
                status=doc.get("status") or "created",
                target_questions=int(
                    doc.get("target_questions") or DEFAULT_TARGET_QUESTIONS
                ),
                answered_count=int(doc.get("answered_count") or 0),
                score=_numeric(doc.get("score")),
                created_at=doc["created_at"],
            )
            for doc in facets.get("recent") or []
        ]

        average = _numeric(scores.get("average_score"))

        return DashboardStats(
            interviews_total=int(summary.get("total") or 0),
            interviews_completed=int(summary.get("completed") or 0),
            interviews_in_progress=int(summary.get("in_progress") or 0),
            interviews_not_started=int(summary.get("not_started") or 0),
            questions_answered=int(summary.get("questions_answered") or 0),
            scored_count=int(scores.get("scored_count") or 0),
            average_score=round(average, 1) if average is not None else None,
            strong_topics=[item.topic for item in strong_topics],
            weak_topics=[item.topic for item in weak_topics],
            strong_topic_counts=strong_topics,
            weak_topic_counts=weak_topics,
            active_interview=active_interview,
            recent=recent,
        )
