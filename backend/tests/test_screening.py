"""Candidate invitations: recruiter invite, magic-link entry, and the session."""

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import _with_mongo

INTERVIEW_LLM = "app.services.interview_service.llm_service.generate_structured"


def _patch_llm(monkeypatch) -> None:
    state = {"n": 0}

    async def fake(prompt: str, schema, **kwargs: object):
        name = schema.__name__
        if name == "QuestionGeneration":
            state["n"] += 1
            return schema(question=f"Question {state['n']}?", topic=f"topic-{state['n']}")
        if name == "EvaluationGeneration":
            return schema(
                scores={
                    "technical": 80,
                    "relevance": 80,
                    "completeness": 80,
                    "structure": 80,
                    "clarity": 80,
                },
                strengths=[],
                weaknesses=[],
                feedback="ok",
                improved_answer="model answer",
                next_step="new_topic",
            )
        if name == "ReportGeneration":
            return schema(narrative="ok", preparation_plan=[])
        raise AssertionError(f"unexpected schema {name}")

    monkeypatch.setattr(INTERVIEW_LLM, fake)


def _patch_llm_fail_first_question(monkeypatch) -> None:
    state = {"failed": False}

    async def fake(prompt: str, schema, **kwargs: object):
        if schema.__name__ != "QuestionGeneration":
            raise AssertionError(f"unexpected schema {schema.__name__}")
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("temporary question failure")
        return schema(question="Recovered question?", topic="recovered")

    monkeypatch.setattr(INTERVIEW_LLM, fake)


def _job_with_template(
    client: TestClient, headers: dict, *, proctoring_mode: str = "off", target: int = 2
) -> str:
    template = client.post(
        "/api/templates",
        headers=headers,
        json={
            "name": "Screening",
            "config": {
                "proctoring_mode": proctoring_mode,
                "rounds": [
                    {
                        "key": "screen",
                        "interview_type": "technical",
                        "difficulty": "intermediate",
                        "duration_minutes": 30,
                        "target_questions": target,
                        "response_modes": ["typed"],
                    }
                ],
            },
        },
    )
    assert template.status_code == 201, template.text
    job = client.post(
        "/api/jobs",
        headers=headers,
        json={
            "title": "Backend Engineer",
            "company": "Acme",
            "description": "Build and operate our APIs.",
            "template_id": template.json()["id"],
        },
    )
    assert job.status_code == 201, job.text
    return job.json()["id"]


def _invite(client: TestClient, headers: dict, job_id: str, **overrides: object) -> dict:
    payload: dict = {
        "job_id": job_id,
        "candidate_email": "candidate@example.com",
        "candidate_name": "Cand Idate",
    }
    payload.update(overrides)
    response = client.post("/api/invitations", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _token(invitation: dict) -> str:
    return invitation["accept_url"].split("/interview/", 1)[1]


def _set_invitation(invitation_id: str, fields: dict) -> None:
    async def run(db) -> None:
        await db.screening_invitations.update_one(
            {"_id": ObjectId(invitation_id)}, {"$set": fields}
        )

    _with_mongo(run)


def test_invitations_require_recruiter(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/invitations",
        headers=auth_headers,
        json={"job_id": "x", "candidate_email": "c@example.com"},
    )
    assert response.status_code == 403


def test_candidate_runs_the_full_flow(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, target=2)
    invitation = _invite(client, staff_headers, job_id)
    assert invitation["status"] == "pending"
    assert invitation["accept_url"].startswith(f"{settings.frontend_url}/interview/")
    token = _token(invitation)

    # Pre-check (no account).
    session = client.get(f"/api/screening/{token}")
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["role"] == "Backend Engineer"
    assert body["company"] == "Acme"
    assert body["consent_required"] is False
    assert body["started"] is False
    assert session.headers["cache-control"] == "private, no-store"

    empty_history = client.get(f"/api/screening/{token}/conversation")
    assert empty_history.status_code == 200
    assert empty_history.json() == {
        "messages": [],
        "started_at": None,
        "current_question_id": None,
    }

    started = client.post(f"/api/screening/{token}/start", json={"consent": False})
    assert started.status_code == 200, started.text
    question_id = started.json()["question"]["id"]
    assert started.json()["question"]["created_at"]

    started_history = client.get(f"/api/screening/{token}/conversation")
    assert started_history.status_code == 200
    assert started_history.headers["cache-control"] == "private, no-store"
    started_body = started_history.json()
    assert started_body["started_at"]
    assert started_body["current_question_id"] == question_id
    assert len(started_body["messages"]) == 1
    assert started_body["messages"][0]["id"] == f"ai-{question_id}"
    assert started_body["messages"][0]["author"] == "ai"
    assert started_body["messages"][0]["created_at"]

    current = client.get(f"/api/screening/{token}/current-question")
    assert current.status_code == 200
    assert current.json()["question"]["id"] == question_id

    first = client.post(
        f"/api/screening/{token}/questions/{question_id}/answer",
        json={"answer": "An index speeds up reads by avoiding full scans."},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "in_progress"
    next_id = first.json()["next_question"]["id"]
    assert first.json()["next_question"]["created_at"]

    history = client.get(f"/api/screening/{token}/conversation")
    assert history.status_code == 200
    assert history.json()["current_question_id"] == next_id
    messages = history.json()["messages"]
    assert [message["author"] for message in messages] == ["ai", "candidate", "ai"]
    assert messages[0]["id"] == f"ai-{question_id}"
    assert messages[1]["id"].startswith("c-")
    assert messages[1]["text"] == "An index speeds up reads by avoiding full scans."
    assert messages[2]["id"] == f"ai-{next_id}"
    assert all(message["created_at"] for message in messages)

    second = client.post(
        f"/api/screening/{token}/questions/{next_id}/answer",
        json={"answer": "I would measure with EXPLAIN and add a covering index."},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "completed"

    final = client.get(f"/api/screening/{token}")
    assert final.json()["status"] == "completed"
    assert client.get(f"/api/screening/{token}/conversation").status_code == 409


def test_reserved_start_retries_after_question_generation_failure(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm_fail_first_question(monkeypatch)
    job_id = _job_with_template(client, staff_headers, target=2)
    token = _token(_invite(client, staff_headers, job_id))

    failed = client.post(f"/api/screening/{token}/start", json={"consent": False})
    assert failed.status_code == 503, failed.text

    # The resume path asks for the current question first; it must finish the
    # reserved start rather than reporting the interview as complete.
    recovered = client.get(f"/api/screening/{token}/current-question")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["question"]["text"] == "Recovered question?"

    again = client.post(f"/api/screening/{token}/start", json={"consent": False})
    assert again.status_code == 200, again.text
    assert again.json()["question"]["id"] == recovered.json()["question"]["id"]


def test_conversation_rejects_mismatched_interview_owner(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, target=2)
    token = _token(_invite(client, staff_headers, job_id))

    started = client.post(f"/api/screening/{token}/start", json={"consent": False})
    assert started.status_code == 200, started.text
    interview_id = started.json()["interview_id"]

    async def run(db) -> None:
        await db.interviews.update_one(
            {"_id": ObjectId(interview_id)},
            {"$set": {"user_id": "someone-else"}},
        )

    _with_mongo(run)
    assert client.get(f"/api/screening/{token}/conversation").status_code == 404


def test_proctored_round_requires_consent(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="strict", target=2)
    token = _token(_invite(client, staff_headers, job_id))

    refused = client.post(f"/api/screening/{token}/start", json={"consent": False})
    assert refused.status_code == 409

    accepted = client.post(f"/api/screening/{token}/start", json={"consent": True})
    assert accepted.status_code == 200, accepted.text


def test_unknown_token_is_404(client: TestClient) -> None:
    assert client.get("/api/screening/not-a-real-token").status_code == 404


def test_revoked_invitation_is_rejected(
    client: TestClient, staff_headers: dict
) -> None:
    job_id = _job_with_template(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)

    revoked = client.delete(f"/api/invitations/{invitation['id']}", headers=staff_headers)
    assert revoked.status_code == 204
    assert client.get(f"/api/screening/{token}").status_code == 409
    assert client.get(f"/api/screening/{token}/conversation").status_code == 409


def test_expired_invitation_is_rejected(
    client: TestClient, staff_headers: dict
) -> None:
    job_id = _job_with_template(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id)
    past = datetime.now(UTC) - timedelta(days=1)
    _set_invitation(invitation["id"], {"expires_at": past})
    token = _token(invitation)
    assert client.get(f"/api/screening/{token}").status_code == 409
    assert client.get(f"/api/screening/{token}/conversation").status_code == 409


def test_deadline_is_server_enforced(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, target=3)
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)

    assert client.post(f"/api/screening/{token}/start", json={"consent": False}).status_code == 200

    # Push the server deadline into the past: further work must be refused.
    _set_invitation(invitation["id"], {"round_deadline": datetime.now(UTC) - timedelta(minutes=1)})
    assert client.get(f"/api/screening/{token}/current-question").status_code == 409
    assert client.get(f"/api/screening/{token}").status_code == 409
    assert client.get(f"/api/screening/{token}/conversation").status_code == 409


def test_conversation_enforces_deadline(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, target=3)
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)

    assert (
        client.post(f"/api/screening/{token}/start", json={"consent": False}).status_code
        == 200
    )
    _set_invitation(
        invitation["id"],
        {"round_deadline": datetime.now(UTC) - timedelta(minutes=1)},
    )

    assert client.get(f"/api/screening/{token}/conversation").status_code == 409
    assert client.get(f"/api/screening/{token}").status_code == 409


def test_list_and_remind_rotate_the_token(
    client: TestClient, staff_headers: dict
) -> None:
    job_id = _job_with_template(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id)

    listed = client.get(
        "/api/invitations", headers=staff_headers, params={"job_id": job_id}
    ).json()
    assert any(item["id"] == invitation["id"] for item in listed)
    assert all(item.get("accept_url") is None for item in listed)

    reminded = client.post(
        f"/api/invitations/{invitation['id']}/remind", headers=staff_headers
    )
    assert reminded.status_code == 200, reminded.text
    new_token = _token(reminded.json())
    assert new_token != _token(invitation)

    # The rotated token works; the original no longer does.
    assert client.get(f"/api/screening/{new_token}").status_code == 200
    assert client.get(f"/api/screening/{_token(invitation)}").status_code == 404
