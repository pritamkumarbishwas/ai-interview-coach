import asyncio

from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.repositories.base import to_object_id
from tests.conftest import Env
from tests.test_report import complete_interview


def get_stats(client: TestClient, headers: dict) -> dict:
    response = client.get("/api/dashboard/stats", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


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
    assert body["questions_answered"] == 0
    assert body["average_score"] is None
    assert body["strong_topics"] == []
    assert body["weak_topics"] == []
    assert body["recent"] == []


def test_dashboard_tracks_in_progress_interview(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=3)
    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 1
    assert body["interviews_in_progress"] == 1
    assert body["interviews_completed"] == 0
    assert body["questions_answered"] == 0
    assert body["average_score"] is None

    recent = body["recent"][0]
    assert recent["id"] == ctx["id"]
    assert recent["status"] == "in_progress"
    assert recent["score"] is None
    assert recent["answered_count"] == 0
    assert recent["target_questions"] == 3


def test_dashboard_after_completion(client: TestClient, auth_headers: dict, env: Env) -> None:
    ctx = env.setup(target=2)
    final = complete_interview(client, auth_headers, ctx)
    assert final["status"] == "completed"

    body = get_stats(client, auth_headers)
    assert body["interviews_total"] == 1
    assert body["interviews_completed"] == 1
    assert body["interviews_in_progress"] == 0
    assert body["questions_answered"] == 2
    # Fake evaluations score every answer 80 overall (see conftest dispatcher).
    assert body["average_score"] == 80.0
    assert body["strong_topics"] == ["topic-1", "topic-2"]
    assert body["weak_topics"] == []

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
    second = env.setup(target=1)
    complete_interview(client, auth_headers, second)

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
    assert body["average_score"] == 80.0
    # Most frequent first.
    assert body["strong_topics"] == ["Indexing", "Caching"]
    assert body["weak_topics"] == ["System Design", "Concurrency"]
    # Newest first.
    assert [row["id"] for row in body["recent"]] == [second["id"], first["id"]]
