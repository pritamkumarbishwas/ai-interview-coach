"""Role guards, registration gating, and the practice/screening discriminator."""

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import login, make_user


def test_jobs_require_a_staff_role(client: TestClient, auth_headers: dict) -> None:
    # A candidate (practice user) cannot manage job requisitions.
    assert client.get("/api/jobs", headers=auth_headers).status_code == 403
    assert (
        client.post("/api/jobs", headers=auth_headers, json={"title": "Backend Engineer"})
        .status_code
        == 403
    )


def test_templates_require_a_staff_role(client: TestClient, auth_headers: dict) -> None:
    assert client.get("/api/templates", headers=auth_headers).status_code == 403


def test_reviewer_cannot_manage_jobs(client: TestClient) -> None:
    headers = login(client, make_user("reviewer.jobs@example.com", role="reviewer"))
    assert client.get("/api/jobs", headers=headers).status_code == 403


def test_recruiter_can_manage_jobs(client: TestClient, staff_headers: dict) -> None:
    assert client.get("/api/jobs", headers=staff_headers).status_code == 200


def test_me_exposes_the_role(client: TestClient, admin_headers: dict) -> None:
    body = client.get("/api/auth/me", headers=admin_headers).json()
    assert body["role"] == "admin"


def test_registration_is_disabled_when_screening_enabled(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "feature_screening_enabled", True)
    response = client.post(
        "/api/auth/register",
        json={"name": "New User", "email": "closed@example.com", "password": "supersecret1"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_practice_interviews_are_tagged_practice(
    client: TestClient, auth_headers: dict, env
) -> None:
    ctx = env.setup(target=3)

    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert detail["kind"] == "practice"

    summaries = client.get("/api/interviews", headers=auth_headers).json()
    assert next(item for item in summaries if item["id"] == ctx["id"])["kind"] == "practice"
