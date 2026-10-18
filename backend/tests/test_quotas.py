"""Phase 9: per-role daily quotas."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.quota_service import QuotaService
from tests.test_scorecard import _job_with_rubric


def _invite(client: TestClient, headers: dict, job_id: str, email: str):
    return client.post(
        "/api/invitations",
        headers=headers,
        json={
            "job_id": job_id,
            "candidate_email": email,
            "candidate_name": email.split("@")[0],
        },
    )


def test_limit_for_prefers_the_most_specific_match(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "role_limits",
        {"recruiter:invitations": 5, "recruiter:*": 20, "*:invitations": 1},
    )
    assert QuotaService.limit_for("recruiter", "invitations") == 5
    assert QuotaService.limit_for("recruiter", "exports") == 20
    assert QuotaService.limit_for("reviewer", "invitations") == 1
    # A zero limit means unlimited, as does no match at all.
    monkeypatch.setattr(settings, "role_limits", {"recruiter:invitations": 0})
    assert QuotaService.limit_for("recruiter", "invitations") is None
    assert QuotaService.limit_for("reviewer", "exports") is None


def test_invitation_quota_blocks_and_does_not_overcount(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "role_limits", {"recruiter:invitations": 1})
    job_id = _job_with_rubric(client, staff_headers)

    first = _invite(client, staff_headers, job_id, "one@example.com")
    assert first.status_code == 201, first.text

    second = _invite(client, staff_headers, job_id, "two@example.com")
    assert second.status_code == 429, second.text
    assert second.json()["code"] == "quota_exceeded"

    # The rejected attempt was rolled back: only one unit is consumed.
    quotas = client.get("/api/usage/quotas", headers=staff_headers).json()
    row = next(q for q in quotas["quotas"] if q["action"] == "invitations")
    assert row == {"action": "invitations", "limit": 1, "used": 1, "remaining": 0}


def test_exports_quota_applies_via_a_wildcard(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "role_limits", {"*:exports": 1})
    job_id = _job_with_rubric(client, staff_headers)
    url = "/api/invitations/export"
    params = {"job_id": job_id}

    assert client.get(url, headers=staff_headers, params=params).status_code == 200
    blocked = client.get(url, headers=staff_headers, params=params)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "quota_exceeded"


def test_quotas_default_to_unlimited(client: TestClient, staff_headers: dict) -> None:
    # No ROLE_LIMITS configured: the self-view reports no limit.
    body = client.get("/api/usage/quotas", headers=staff_headers).json()
    assert body["role"] == "recruiter"
    assert all(q["limit"] is None and q["remaining"] is None for q in body["quotas"])
