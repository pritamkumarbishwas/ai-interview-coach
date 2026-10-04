"""Dashboard statistics aggregated from the user's interviews and reports."""

from collections import Counter

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.interview_repository import InterviewRepository
from app.schemas.dashboard import DashboardInterview, DashboardStats

RECENT_LIMIT = 5
# How many of the most frequent strong/weak topics the dashboard shows.
TOPIC_LIMIT = 5


class DashboardService:
    def __init__(self, interviews: InterviewRepository) -> None:
        self._interviews = interviews

    async def stats(self, db: AsyncIOMotorDatabase, user_id: str) -> DashboardStats:
        docs = await self._interviews.all_for_user(db, user_id)
        completed = [doc for doc in docs if doc.get("status") == "completed"]

        reports = [doc["report"] for doc in completed if isinstance(doc.get("report"), dict)]
        scores = [float(report["overall_score"]) for report in reports]
        strong = Counter(topic for report in reports for topic in report.get("strong_topics") or [])
        weak = Counter(topic for report in reports for topic in report.get("weak_topics") or [])

        return DashboardStats(
            interviews_total=len(docs),
            interviews_completed=len(completed),
            interviews_in_progress=sum(1 for doc in docs if doc.get("status") == "in_progress"),
            questions_answered=sum(len(doc.get("answers") or []) for doc in docs),
            average_score=round(sum(scores) / len(scores), 1) if scores else None,
            strong_topics=[topic for topic, _ in strong.most_common(TOPIC_LIMIT)],
            weak_topics=[topic for topic, _ in weak.most_common(TOPIC_LIMIT)],
            recent=[
                DashboardInterview(
                    id=doc["_id"],
                    role=doc.get("role", ""),
                    type=doc.get("type", ""),
                    difficulty=doc.get("difficulty", ""),
                    status=doc.get("status", ""),
                    target_questions=int(doc.get("target_questions") or 0),
                    answered_count=len(doc.get("answers") or []),
                    score=(
                        float(doc["report"]["overall_score"])
                        if isinstance(doc.get("report"), dict) and "overall_score" in doc["report"]
                        else None
                    ),
                    created_at=doc["created_at"],
                )
                for doc in docs[:RECENT_LIMIT]
            ],
        )
