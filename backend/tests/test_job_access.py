"""Job-based access: admin override, recruiter isolation, reviewer assignment."""

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import _with_mongo, login, make_user


def _user_id(email: str) -> str:
    """Resolve a directly-inserted user's id (make_user returns no id)."""
    found = {}

    async def run(db) -> None:
        doc = await db.users.find_one({"email": email})
        assert doc is not None, email
        found["id"] = str(doc["_id"])

    _with_mongo(run)
    return found["id"]


def _create_job(client: TestClient, headers: dict, title: str = "Backend Engineer") -> dict:
    response = client.post(
        "/api/jobs", headers=headers, json={"title": title, "company": "Acme"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reviewer(client: TestClient, role: str = "reviewer") -> tuple[dict, str]:
    email = f"reviewer.{uuid4().hex[:10]}@example.com"
    make_user(email, role=role)
    return login(client, {"email": email, "password": "password1234"}), email


def test_admin_can_manage_another_recruiters_job(
    client: TestClient, staff_headers: dict, admin_headers: dict
) -> None:
    job = _create_job(client, staff_headers)

    # The admin can open a requisition it does not own...
    detail = client.get(f"/api/jobs/{job['id']}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["owner_id"]  # ownership is surfaced for oversight

    # ...and mutate it (full parity).
    updated = client.patch(
        f"/api/jobs/{job['id']}", headers=admin_headers, json={"title": "Staff Engineer"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Staff Engineer"

    assert client.delete(f"/api/jobs/{job['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/jobs/{job['id']}", headers=staff_headers).status_code == 404


def test_a_recruiter_cannot_see_or_touch_another_recruiters_job(
    client: TestClient, staff_headers: dict
) -> None:
    job = _create_job(client, staff_headers)
    other = login(
        client, make_user(f"other.{uuid4().hex[:10]}@example.com", role="recruiter")
    )

    assert client.get(f"/api/jobs/{job['id']}", headers=other).status_code == 404
    assert (
        client.patch(
            f"/api/jobs/{job['id']}", headers=other, json={"title": "Hijacked"}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/jobs/{job['id']}", headers=other).status_code == 404


def test_reviewer_sees_only_assigned_jobs_and_can_decide(
    client: TestClient, staff_headers: dict
) -> None:
    job = _create_job(client, staff_headers)
    other_job = _create_job(client, staff_headers, title="Other Role")
    reviewer, email = _reviewer(client)

    # Unassigned: no jobs, and no access to a specific one.
    assert client.get("/api/jobs", headers=reviewer).json() == []
    assert client.get(f"/api/jobs/{job['id']}", headers=reviewer).status_code == 404

    # The recruiter assigns the reviewer.
    reviewer_id = _user_id(email)
    assigned = client.put(
        f"/api/jobs/{job['id']}/reviewers",
        headers=staff_headers,
        json={"reviewer_ids": [reviewer_id]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["reviewer_ids"] == [reviewer_id]

    # Now the reviewer sees exactly the assigned job, read-only.
    listed = client.get("/api/jobs", headers=reviewer).json()
    assert [item["id"] for item in listed] == [job["id"]]
    assert client.get(f"/api/jobs/{job['id']}", headers=reviewer).status_code == 200
    assert client.get(f"/api/jobs/{other_job['id']}", headers=reviewer).status_code == 404
    assert (
        client.patch(f"/api/jobs/{job['id']}", headers=reviewer, json={"title": "x"}).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/jobs/{job['id']}/reviewers", headers=reviewer, json={"reviewer_ids": []}
        ).status_code
        == 403
    )

    # The reviewer can read the pipeline and record a decision...
    invitation = client.post(
        "/api/invitations",
        headers=staff_headers,
        json={"job_id": job["id"], "candidate_email": "cand@example.com"},
    ).json()
    decided = client.patch(
        f"/api/invitations/{invitation['id']}/decision",
        headers=reviewer,
        json={"decision": "advance"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["decision"] == "advance"

    # ...but not on an unassigned job's pipeline (treated as not found).
    assert (
        client.get(
            "/api/invitations", headers=reviewer, params={"job_id": other_job["id"]}
        ).status_code
        == 404
    )


def test_reviewer_assignment_rejects_non_reviewers(
    client: TestClient, staff_headers: dict
) -> None:
    job = _create_job(client, staff_headers)
    recruiter_email = f"recruiter.{uuid4().hex[:10]}@example.com"
    make_user(recruiter_email, role="recruiter")
    recruiter_id = _user_id(recruiter_email)

    response = client.put(
        f"/api/jobs/{job['id']}/reviewers",
        headers=staff_headers,
        json={"reviewer_ids": [recruiter_id]},
    )
    assert response.status_code == 422, response.text


def test_recruiter_can_list_assignable_reviewers(
    client: TestClient, staff_headers: dict, auth_headers: dict
) -> None:
    email = f"listed.{uuid4().hex[:10]}@example.com"
    make_user(email, role="reviewer")

    listed = client.get("/api/staff/reviewers", headers=staff_headers)
    assert listed.status_code == 200, listed.text
    assert any(item["email"] == email for item in listed.json())

    # Practice candidates cannot enumerate staff.
    assert client.get("/api/staff/reviewers", headers=auth_headers).status_code == 403
