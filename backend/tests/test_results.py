from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tests.conftest import _with_mongo


def seed_results(email: str) -> None:
    """Three completed rows (two scored) plus unfinished and foreign rows."""

    async def seed(db) -> None:
        user = await db.users.find_one({"email": email})
        assert user is not None
        user_id = str(user["_id"])
        other = await db.users.find_one({"email": "someone.else@example.com"})
        other_id = str(other["_id"]) if other else "missing"

        base = {
            "user_id": user_id,
            "resume_id": "",
            "jd_id": "jd",
            "role": "Backend Engineer",
            "kind": "practice",
            "level": "mid",
            "type": "technical",
            "difficulty": "intermediate",
            "proctoring_mode": "off",
            "target_questions": 3,
            "questions": [{"id": "q1", "sequence": 1, "text": "?", "topic": "t"}],
            "answers": [{"id": "a1", "question_id": "q1", "text": "a", "evaluation": None}],
        }
        await db.interviews.insert_many(
            [
                {
                    **base,
                    "status": "completed",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "completed_at": datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                    "report": {"overall_score": 82.0},
                },
                {
                    **base,
                    "status": "completed",
                    "created_at": datetime(2026, 1, 2, tzinfo=UTC),
                    "completed_at": datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
                    "report": {"overall_score": 64.0},
                },
                {
                    **base,
                    "status": "completed",
                    "created_at": datetime(2026, 1, 3, tzinfo=UTC),
                    "completed_at": datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
                    "report": None,
                },
                {
                    **base,
                    "status": "in_progress",
                    "created_at": datetime(2026, 1, 4, tzinfo=UTC),
                    "report": None,
                },
                {
                    **base,
                    "user_id": other_id,
                    "status": "completed",
                    "created_at": datetime(2026, 1, 5, tzinfo=UTC),
                    "completed_at": datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
                    "report": {"overall_score": 99.0},
                },
            ]
        )

    _with_mongo(seed)


def test_results_require_auth(client: TestClient) -> None:
    assert client.get("/api/interviews/results").status_code == 401


def test_results_returns_server_side_stats_and_recent_order(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_results(registered_user["email"])

    response = client.get("/api/interviews/results", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["scored_count"] == 2
    assert body["average_score"] == 73.0
    assert body["best_score"] == 82.0
    assert len(body["items"]) == 3
    assert [item["score"] for item in body["items"]] == [None, 64.0, 82.0]
    assert all(item["completed_at"] is not None for item in body["items"])


def test_results_supports_score_sorting(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_results(registered_user["email"])

    highest = client.get(
        "/api/interviews/results?sort=score_desc", headers=auth_headers
    )
    lowest = client.get(
        "/api/interviews/results?sort=score_asc", headers=auth_headers
    )
    assert highest.status_code == 200, highest.text
    assert lowest.status_code == 200, lowest.text
    assert [item["score"] for item in highest.json()["items"]] == [82.0, 64.0, None]
    assert [item["score"] for item in lowest.json()["items"]] == [64.0, 82.0, None]


def test_results_stats_cover_all_rows_when_page_is_limited(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    seed_results(registered_user["email"])

    response = client.get("/api/interviews/results?limit=1", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] == 3
    assert body["average_score"] == 73.0


def test_results_rejects_an_unknown_sort(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/api/interviews/results?sort=banana", headers=auth_headers)
    assert response.status_code == 422
