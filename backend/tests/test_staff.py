"""Staff invitations, acceptance, role changes, bootstrap admin, and audit trail."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.staff_service import ensure_bootstrap_admin
from tests.conftest import _with_mongo, make_user


def _token_from(accept_url: str) -> str:
    assert "token=" in accept_url
    return accept_url.split("token=", 1)[1]


def test_staff_endpoints_require_admin(client: TestClient, staff_headers: dict) -> None:
    assert client.get("/api/staff/users", headers=staff_headers).status_code == 403
    assert (
        client.post(
            "/api/staff/invitations",
            headers=staff_headers,
            json={"email": "nope@example.com", "role": "recruiter"},
        ).status_code
        == 403
    )
    assert client.get("/api/staff/users").status_code == 401


def test_invite_accept_and_login(client: TestClient, admin_headers: dict) -> None:
    created = client.post(
        "/api/staff/invitations",
        headers=admin_headers,
        json={"email": "newrecruiter@example.com", "role": "recruiter", "name": "New Rec"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "recruiter"
    assert body["status"] == "pending"
    assert body["accept_url"]

    accepted = client.post(
        "/api/staff/invitations/accept",
        json={
            "token": _token_from(body["accept_url"]),
            "name": "New Rec",
            "password": "strongpass123",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["user"]["role"] == "recruiter"

    # The new staff member can immediately use recruiter endpoints.
    headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    assert client.get("/api/jobs", headers=headers).status_code == 200

    # The token is single-use.
    again = client.post(
        "/api/staff/invitations/accept",
        json={
            "token": _token_from(body["accept_url"]),
            "name": "New Rec",
            "password": "strongpass123",
        },
    )
    assert again.status_code == 409


def test_invite_existing_user_is_conflict(client: TestClient, admin_headers: dict) -> None:
    make_user("already.staff@example.com", role="recruiter")
    response = client.post(
        "/api/staff/invitations",
        headers=admin_headers,
        json={"email": "already.staff@example.com", "role": "reviewer"},
    )
    assert response.status_code == 409


def test_invite_rejects_non_staff_role(client: TestClient, admin_headers: dict) -> None:
    response = client.post(
        "/api/staff/invitations",
        headers=admin_headers,
        json={"email": "candidate@example.com", "role": "candidate"},
    )
    assert response.status_code == 422


def test_revoked_invitation_cannot_be_accepted(client: TestClient, admin_headers: dict) -> None:
    created = client.post(
        "/api/staff/invitations",
        headers=admin_headers,
        json={"email": "revoked@example.com", "role": "reviewer"},
    ).json()
    token = _token_from(created["accept_url"])

    assert (
        client.delete(f"/api/staff/invitations/{created['id']}", headers=admin_headers).status_code
        == 204
    )

    accepted = client.post(
        "/api/staff/invitations/accept",
        json={"token": token, "name": "Revoked", "password": "strongpass123"},
    )
    assert accepted.status_code == 409


def test_revoking_unknown_invitation_is_404(client: TestClient, admin_headers: dict) -> None:
    response = client.delete("/api/staff/invitations/deadbeef", headers=admin_headers)
    assert response.status_code == 404


def test_list_staff_and_change_role(client: TestClient, admin_headers: dict) -> None:
    make_user("change.role@example.com", role="reviewer")

    staff = client.get("/api/staff/users", headers=admin_headers).json()
    target = next(user for user in staff if user["email"] == "change.role@example.com")
    assert target["role"] == "reviewer"

    updated = client.patch(
        f"/api/staff/users/{target['id']}/role",
        headers=admin_headers,
        json={"role": "recruiter"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "recruiter"


def test_audit_log_records_staff_actions(client: TestClient, admin_headers: dict) -> None:
    client.post(
        "/api/staff/invitations",
        headers=admin_headers,
        json={"email": "audited@example.com", "role": "recruiter"},
    )
    logs = client.get("/api/audit-logs", headers=admin_headers).json()
    assert any(entry["action"] == "staff.invite" for entry in logs)


def test_audit_log_requires_admin(client: TestClient, staff_headers: dict) -> None:
    assert client.get("/api/audit-logs", headers=staff_headers).status_code == 403


def test_bootstrap_admin_is_created_and_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bootstrap_admin_email", "seed.admin@example.com")
    monkeypatch.setattr(settings, "bootstrap_admin_password", "seedpass1234")
    monkeypatch.setattr(settings, "bootstrap_admin_name", "Seed Admin")

    seen: dict = {}

    async def run(db) -> None:
        await ensure_bootstrap_admin(db)
        await ensure_bootstrap_admin(db)  # second call must not duplicate
        seen["doc"] = await db.users.find_one({"email": "seed.admin@example.com"})

    _with_mongo(run)
    assert seen["doc"]["role"] == "admin"
    assert seen["doc"]["name"] == "Seed Admin"


def test_seat_cap_blocks_new_invites(
    client: TestClient, admin_headers: dict, monkeypatch
) -> None:
    payload = {"email": f"seat.{uuid4().hex[:8]}@example.com", "role": "reviewer"}

    # The inviting admin already occupies a seat, so a cap of 1 is full.
    monkeypatch.setattr(settings, "max_staff_seats", 1)
    blocked = client.post("/api/staff/invitations", headers=admin_headers, json=payload)
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["code"] == "quota_exceeded"

    # 0 means unlimited again.
    monkeypatch.setattr(settings, "max_staff_seats", 0)
    ok = client.post("/api/staff/invitations", headers=admin_headers, json=payload)
    assert ok.status_code == 201, ok.text
