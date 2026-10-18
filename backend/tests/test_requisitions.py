"""Job requisitions: recruiter-facing CRUD and template attachment."""

from fastapi.testclient import TestClient

from tests.conftest import make_user


def _login(client: TestClient, creds: dict) -> dict[str, str]:
    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _make_template(client: TestClient, headers: dict) -> str:
    response = client.post("/api/templates", headers=headers, json={"name": "Backend Screen"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_jobs_require_auth(client: TestClient) -> None:
    assert client.get("/api/jobs").status_code == 401
    assert client.post("/api/jobs", json={"title": "Backend Engineer"}).status_code == 401


def test_job_create_list_get_update_delete(client: TestClient, staff_headers: dict) -> None:
    created = client.post(
        "/api/jobs",
        headers=staff_headers,
        json={
            "title": "  Backend Engineer  ",
            "company": "Acme",
            "location": "Remote",
            "description": "Own our APIs end to end.",
        },
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["title"] == "Backend Engineer"
    assert job["status"] == "draft"
    assert job["template_id"] is None
    job_id = job["id"]

    listed = client.get("/api/jobs", headers=staff_headers).json()
    summary = next(item for item in listed if item["id"] == job_id)
    assert summary["status"] == "draft"
    # The list projection drops the description.
    assert "description" not in summary

    detail = client.get(f"/api/jobs/{job_id}", headers=staff_headers)
    assert detail.status_code == 200
    assert detail.json()["description"] == "Own our APIs end to end."

    updated = client.patch(f"/api/jobs/{job_id}", headers=staff_headers, json={"status": "open"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "open"

    assert client.delete(f"/api/jobs/{job_id}", headers=staff_headers).status_code == 204
    assert client.get(f"/api/jobs/{job_id}", headers=staff_headers).status_code == 404


def test_job_can_attach_and_detach_a_template(client: TestClient, staff_headers: dict) -> None:
    template_id = _make_template(client, staff_headers)
    created = client.post(
        "/api/jobs",
        headers=staff_headers,
        json={"title": "Backend Engineer", "template_id": template_id},
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    assert created.json()["template_id"] == template_id

    detached = client.patch(
        f"/api/jobs/{job_id}", headers=staff_headers, json={"template_id": None}
    )
    assert detached.status_code == 200
    assert detached.json()["template_id"] is None


def test_job_attaching_unknown_template_is_404(client: TestClient, staff_headers: dict) -> None:
    response = client.post(
        "/api/jobs",
        headers=staff_headers,
        json={"title": "Backend Engineer", "template_id": "nope"},
    )
    assert response.status_code == 404


def test_job_cannot_attach_another_users_template(client: TestClient, staff_headers: dict) -> None:
    other = _login(client, make_user("other.jobs.tpl@example.com", role="recruiter"))
    template_id = _make_template(client, other)
    response = client.post(
        "/api/jobs",
        headers=staff_headers,
        json={"title": "Backend Engineer", "template_id": template_id},
    )
    assert response.status_code == 404


def test_jobs_are_isolated_between_users(client: TestClient, staff_headers: dict) -> None:
    job_id = client.post(
        "/api/jobs", headers=staff_headers, json={"title": "Backend Engineer"}
    ).json()["id"]
    other = _login(client, make_user("other.jobs.list@example.com", role="recruiter"))
    assert client.get(f"/api/jobs/{job_id}", headers=other).status_code == 404
    assert client.get("/api/jobs", headers=other).json() == []
