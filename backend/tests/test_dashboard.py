import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.repositories.base import to_object_id
from tests.conftest import Env, _with_mongo
from tests.test_report import complete_interview, get_report


def get_stats(client: TestClient, headers: dict) -> dict:
    response = client.get("/api/dashboard/stats", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def seed_interviews(email: str, rows: list[dict]) -> list[str]:
    """Insert dashboard rows directly so edge cases stay fast and deterministic."""
    inserted: list[str] = []

    async def seed(db) -> None:
        user = await db.users.find_one({"email": email})
        assert user is not None
        base = {
            "user_id": str(user["_id"]),
            "resume_id": "",
            "jd_id": "jd",
            "role": "Backend Engineer",
            "kind": "practice",
            "level": "mid",
            "type": "technical",
            "difficulty": "intermediate",
            "status": "created",
            "proctoring_mode": "off",
            "target_questions": 3,
            "questions": [{"id": "q1", "sequence": 1, "text": "?", "topic": "t"}],
            "answers": [
                {
                    "id": "a1",
                    "question_id": "q1",
                    "text": "secret answer",
                    "evaluation": None,
                }
            ],
        }
        for index, override in enumerate(rows):
            doc = {
                **base,
                "created_at": datetime(2026, 1, 1, 0, 0, index, tzinfo=UTC),
                **override,
            }
            result = await db.interviews.insert_one(doc)
            inserted.append(str(result.inserted_id))

    _with_mongo(seed)
    return inserted


def patch_report_topics(updates: dict[str, dict]) -> None:
    """Rewrite topic lists on cached reports (the aggregation input)."""

    async def runner() -> None:
        client = AsyncIOMotorClient(settings.mongo_uri)
        try:
            db = client[settings.mongo_db_name]
            for interview_id, set_ops in updates.items():
                await db.interviews.update_one(
                    {"_id": to_object_id(interview_id)}, {"$set": set_ops}
                )
        finally:
            client.close()

    asyncio.run(runner())


def test_dashboard_requires_auth(client: TestClient) -> None:
    assert client.get("/api/dashboard/stats").status_code == 401


def test_empty_dashboard(client: TestClient, auth_headers: dict) -> None:
    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 0
    assert body["interviews_completed"] == 0
    assert body["interviews_in_progress"] == 0
    assert body["interviews_not_started"] == 0
    assert body["questions_answered"] == 0
    assert body["scored_count"] == 0
    assert body["average_score"] is None
    assert body["strong_topics"] == []
    assert body["weak_topics"] == []
    assert body["strong_topic_counts"] == []
    assert body["weak_topic_counts"] == []
    assert body["active_interview"] is None
    assert body["recent"] == []


def test_dashboard_tracks_in_progress_interview(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=3)
    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 1
    assert body["interviews_in_progress"] == 1
    assert body["interviews_not_started"] == 0
    assert body["interviews_completed"] == 0
    assert body["questions_answered"] == 0
    assert body["scored_count"] == 0
    assert body["average_score"] is None
    assert body["active_interview"]["id"] == ctx["id"]
    assert body["active_interview"]["status"] == "in_progress"

    recent = body["recent"][0]
    assert recent["id"] == ctx["id"]
    assert recent["status"] == "in_progress"
    assert recent["kind"] == "practice"
    assert recent["score"] is None
    assert recent["answered_count"] == 0
    assert recent["target_questions"] == 3


def test_dashboard_tracks_not_started_and_picks_newest_active(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    ids = seed_interviews(
        registered_user["email"],
        [
            {"status": "created"},
            {"status": "in_progress"},
            {"status": "completed"},
        ],
    )
    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 3
    assert body["interviews_not_started"] == 1
    assert body["interviews_in_progress"] == 1
    assert body["interviews_completed"] == 1
    assert body["active_interview"]["id"] == ids[1]
    assert body["active_interview"]["status"] == "in_progress"


def test_dashboard_after_completion(client: TestClient, auth_headers: dict, env: Env) -> None:
    ctx = env.setup(target=2)
    final = complete_interview(client, auth_headers, ctx)
    assert final["status"] == "completed"
    # Force the deferred evaluation + report to settle (background task or
    # backfill) before the dashboard aggregates them.
    assert get_report(client, auth_headers, ctx["id"]).status_code == 200

    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 1
    assert body["interviews_completed"] == 1
    assert body["interviews_in_progress"] == 0
    assert body["interviews_not_started"] == 0
    assert body["questions_answered"] == 2
    assert body["scored_count"] == 1
    assert body["active_interview"] is None
    # Fake evaluations score every answer 80 overall (see conftest dispatcher).
    assert body["average_score"] == 80.0
    assert body["strong_topics"] == ["topic-1", "topic-2"]
    assert body["weak_topics"] == []
    assert [item["count"] for item in body["strong_topic_counts"]] == [1, 1]

    recent = body["recent"][0]
    assert recent["id"] == ctx["id"]
    assert recent["status"] == "completed"
    assert recent["score"] == 80.0
    assert recent["answered_count"] == 2


def test_dashboard_aggregates_topics_and_scores_across_interviews(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    first = env.setup(target=1)
    complete_interview(client, auth_headers, first)
    assert get_report(client, auth_headers, first["id"]).status_code == 200
    second = env.setup(target=1)
    complete_interview(client, auth_headers, second)
    assert get_report(client, auth_headers, second["id"]).status_code == 200

    patch_report_topics(
        {
            first["id"]: {
                "report.strong_topics": ["Indexing"],
                "report.weak_topics": ["System Design"],
            },
            second["id"]: {
                "report.strong_topics": ["Indexing", "Caching"],
                "report.weak_topics": ["System Design", "Concurrency"],
            },
        }
    )

    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 2
    assert body["interviews_completed"] == 2
    assert body["questions_answered"] == 2
    assert body["scored_count"] == 2
    assert body["average_score"] == 80.0
    # Most frequent first.
    assert body["strong_topics"] == ["Indexing", "Caching"]
    assert body["weak_topics"] == ["System Design", "Concurrency"]
    assert [(item["topic"], item["count"]) for item in body["strong_topic_counts"]] == [
        ("Indexing", 2),
        ("Caching", 1),
    ]
    # Newest first.
    assert [row["id"] for row in body["recent"]] == [second["id"], first["id"]]


def test_dashboard_ignores_completed_interviews_without_reports(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_interviews(
        registered_user["email"],
        [
            {"status": "completed", "report": None},
            {"status": "completed", "report": {"overall_score": 90.0}},
        ],
    )

    body = get_stats(client, auth_headers)
    assert body["interviews_completed"] == 2
    assert body["scored_count"] == 1
    assert body["average_score"] == 90.0
    assert [row["score"] for row in body["recent"]] == [90.0, None]


def test_dashboard_tolerates_non_numeric_report_scores(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_interviews(
        registered_user["email"],
        [{"status": "completed", "report": {"overall_score": "not-a-number"}}],
    )

    body = get_stats(client, auth_headers)
    assert body["interviews_completed"] == 1
    assert body["scored_count"] == 0
    assert body["average_score"] is None
    assert body["recent"][0]["score"] is None


def test_dashboard_keeps_overlapping_topics_on_the_stronger_side(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_interviews(
        registered_user["email"],
        [
            {
                "status": "completed",
                "report": {
                    "overall_score": 80.0,
                    "strong_topics": ["Indexing", "Caching"],
                    "weak_topics": ["Indexing"],
                },
            },
            {
                "status": "completed",
                "report": {
                    "overall_score": 70.0,
                    "strong_topics": ["Indexing"],
                    "weak_topics": ["Indexing", "System Design"],
                },
            },
        ],
    )

    body = get_stats(client, auth_headers)
    assert "Indexing" in body["strong_topics"]
    assert "Indexing" not in body["weak_topics"]
    assert "Caching" in body["strong_topics"]
    assert body["weak_topics"] == ["System Design"]


def test_dashboard_limits_recent_to_five(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    ids = seed_interviews(
        registered_user["email"],
        [{"status": "created"} for _ in range(6)],
    )

    body = get_stats(client, auth_headers)
    assert len(body["recent"]) == 5
    assert [row["id"] for row in body["recent"]] == list(reversed(ids))[:5]


def test_dashboard_never_returns_answer_bodies(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_interviews(registered_user["email"], [{"status": "created"}])

    response = client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "secret answer" not in response.text
    assert "answers" not in response.json()["recent"][0]


def test_dashboard_disables_caching(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
