"""Phase 7: the review workspace — human decisions and the ranked shortlist."""

from fastapi.testclient import TestClient

from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow


def _invite(client: TestClient, headers: dict, job_id: str, email: str) -> dict:
    response = client.post(
        "/api/invitations",
        headers=headers,
        json={"job_id": job_id, "candidate_email": email, "candidate_name": email.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _token(invitation: dict) -> str:
    return invitation["accept_url"].split("/interview/", 1)[1]


def test_decision_workflow(client: TestClient, staff_headers: dict, auth_headers: dict) -> None:
    job_id = _job_with_rubric(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id, "decide@example.com")
    url = f"/api/invitations/{invitation['id']}/decision"

    assert invitation["decision"] == "pending"

    advanced = client.patch(
        url, headers=staff_headers, json={"decision": "advance", "note": "strong"}
    )
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["decision"] == "advance"
    assert advanced.json()["decision_note"] == "strong"
    assert advanced.json()["decided_at"] is not None

    # A decision can be undone back to pending.
    undone = client.patch(url, headers=staff_headers, json={"decision": "pending"})
    assert undone.status_code == 200
    assert undone.json()["decision"] == "pending"

    # The invitation list must reflect the recorded decision, not default it.
    client.patch(url, headers=staff_headers, json={"decision": "hold", "note": "revisit"})
    listed = client.get(
        "/api/invitations", headers=staff_headers, params={"job_id": job_id}
    ).json()
    row = next(item for item in listed if item["id"] == invitation["id"])
    assert row["decision"] == "hold"
    assert row["decision_note"] == "revisit"
    assert row["decided_at"] is not None
    client.patch(url, headers=staff_headers, json={"decision": "pending"})

    # Unknown decision value is rejected by validation.
    assert client.patch(url, headers=staff_headers, json={"decision": "maybe"}).status_code == 422
    # Candidates cannot record decisions.
    assert client.patch(url, headers=auth_headers, json={"decision": "advance"}).status_code == 403


def test_shortlist_ranks_completed_candidates(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    finished = _invite(client, staff_headers, job_id, "done@example.com")
    waiting = _invite(client, staff_headers, job_id, "waiting@example.com")
    _run_candidate_flow(client, _token(finished))

    response = client.get(
        "/api/invitations/shortlist", headers=staff_headers, params={"job_id": job_id}
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert [row["invitation_id"] for row in rows] == [finished["id"], waiting["id"]]

    top = rows[0]
    assert top["overall_score"] == 72.0
    assert top["meets_threshold"] is True
    assert top["competency_count"] == 1
    assert top["integrity_level"] is not None
    assert top["decision"] == "pending"

    # A not-yet-finished candidate still appears, ranked last with no scores.
    assert rows[1]["status"] == "pending"
    assert rows[1]["overall_score"] == 0.0
    assert rows[1]["integrity_level"] is None


def test_shortlist_access_control(
    client: TestClient, staff_headers: dict, auth_headers: dict
) -> None:
    job_id = _job_with_rubric(client, staff_headers)
    assert (
        client.get(
            "/api/invitations/shortlist", headers=auth_headers, params={"job_id": job_id}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/invitations/shortlist",
            headers=staff_headers,
            params={"job_id": "64b000000000000000000000"},
        ).status_code
        == 404
    )
