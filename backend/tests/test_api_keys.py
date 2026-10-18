"""Phase 8: programmatic (public) API keys and the read-only public API."""

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import _with_mongo, login, make_user
from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow
from tests.test_shortlist import _invite, _token


def _create_key(client: TestClient, headers: dict, **overrides: object) -> dict:
    payload = {"name": "ATS integration", "role": "reviewer"}
    payload.update(overrides)
    response = client.post("/api/api-keys", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_key_secret_is_shown_once_and_listed_masked(
    client: TestClient, staff_headers: dict
) -> None:
    created = _create_key(client, staff_headers)
    assert created["key"].startswith("aic_")
    assert created["prefix"] == created["key"][: len(created["prefix"])]
    assert created["revoked_at"] is None

    listed = client.get("/api/api-keys", headers=staff_headers).json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]
    assert "key" not in listed[0]  # the raw secret is never returned again
    assert listed[0]["prefix"] == created["prefix"]


def test_public_api_requires_a_valid_key(
    client: TestClient, staff_headers: dict
) -> None:
    assert client.get("/api/public/jobs").status_code == 401
    assert (
        client.get("/api/public/jobs", headers={"X-API-Key": "nope"}).status_code == 401
    )

    created = _create_key(client, staff_headers)
    ok = client.get("/api/public/jobs", headers={"X-API-Key": created["key"]})
    assert ok.status_code == 200, ok.text
    assert ok.headers["cache-control"] == "private, no-store"


def test_public_api_is_scoped_to_the_key_owner(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    finished = _invite(client, staff_headers, job_id, "done@example.com")
    _run_candidate_flow(client, _token(finished))

    key = _create_key(client, staff_headers)["key"]
    headers = {"X-API-Key": key}

    jobs = client.get("/api/public/jobs", headers=headers).json()
    assert [job["id"] for job in jobs] == [job_id]

    candidates = client.get(
        f"/api/public/jobs/{job_id}/candidates", headers=headers
    ).json()
    assert len(candidates) == 1
    assert candidates[0]["candidate_email"] == "done@example.com"
    assert candidates[0]["overall_score"] == 72.0

    metrics = client.get(f"/api/public/jobs/{job_id}/metrics", headers=headers).json()
    assert metrics["total_invited"] == 1
    assert metrics["completed"] == 1

    # A different staff user's key cannot see the first user's job.
    other = login(client, make_user(f"other.{job_id}@example.com", role="recruiter"))
    other_key = _create_key(client, other)["key"]
    assert client.get("/api/public/jobs", headers={"X-API-Key": other_key}).json() == []
    assert (
        client.get(
            f"/api/public/jobs/{job_id}/candidates", headers={"X-API-Key": other_key}
        ).status_code
        == 404
    )


def test_revoked_key_is_rejected(client: TestClient, staff_headers: dict) -> None:
    created = _create_key(client, staff_headers)
    headers = {"X-API-Key": created["key"]}
    assert client.get("/api/public/jobs", headers=headers).status_code == 200

    revoked = client.delete(f"/api/api-keys/{created['id']}", headers=staff_headers)
    assert revoked.status_code == 204

    denied = client.get("/api/public/jobs", headers=headers)
    assert denied.status_code == 401
    assert "revoked" in denied.json()["detail"].lower()

    listed = client.get("/api/api-keys", headers=staff_headers).json()
    assert listed[0]["revoked_at"] is not None
    # Revoking an unknown key is a 404.
    assert (
        client.delete(
            "/api/api-keys/64b000000000000000000000", headers=staff_headers
        ).status_code
        == 404
    )


def test_expired_key_is_rejected(client: TestClient, staff_headers: dict) -> None:
    created = _create_key(client, staff_headers, expires_in_days=1)

    async def backdate(db) -> None:
        await db.api_keys.update_one(
            {"_id": ObjectId(created["id"])},
            {"$set": {"expires_at": datetime.now(UTC) - timedelta(days=1)}},
        )

    _with_mongo(backdate)

    denied = client.get("/api/public/jobs", headers={"X-API-Key": created["key"]})
    assert denied.status_code == 401
    assert "expired" in denied.json()["detail"].lower()


def test_only_staff_can_manage_keys(
    client: TestClient, auth_headers: dict
) -> None:
    assert client.get("/api/api-keys", headers=auth_headers).status_code == 403
    assert (
        client.post(
            "/api/api-keys", headers=auth_headers, json={"name": "x"}
        ).status_code
        == 403
    )
