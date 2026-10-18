"""Interview templates: CRUD, question bank, and AI question preview."""

from fastapi.testclient import TestClient

from tests.conftest import make_user

PREVIEW_LLM = "app.services.template_service.llm_service.generate_structured"


def _login(client: TestClient, creds: dict) -> dict[str, str]:
    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _template_payload(**overrides: object) -> dict:
    payload: dict = {
        "name": "Backend Screen",
        "description": "Standard backend first round",
        "config": {
            "proctoring_mode": "strict",
            "integrity_policy": "advisory",
            "rounds": [
                {
                    "key": "screen",
                    "label": "Screening",
                    "interview_type": "technical",
                    "difficulty": "intermediate",
                    "duration_minutes": 30,
                    "target_questions": 5,
                    "response_modes": ["voice", "typed"],
                },
                {
                    "key": "coding",
                    "label": "Coding",
                    "interview_type": "technical",
                    "difficulty": "advanced",
                    "response_modes": ["code"],
                },
            ],
        },
        "question_bank": [
            {
                "text": "Explain database indexing.",
                "topic": "databases",
                "competency": "fundamentals",
            },
        ],
    }
    payload.update(overrides)
    return payload


def _create_template(client: TestClient, headers: dict) -> dict:
    response = client.post("/api/templates", headers=headers, json=_template_payload())
    assert response.status_code == 201, response.text
    return response.json()


def test_templates_require_auth(client: TestClient) -> None:
    assert client.get("/api/templates").status_code == 401
    assert client.post("/api/templates", json={"name": "Backend Screen"}).status_code == 401


def test_template_create_list_get_update_delete(client: TestClient, staff_headers: dict) -> None:
    body = _create_template(client, staff_headers)
    assert body["name"] == "Backend Screen"
    assert len(body["config"]["rounds"]) == 2
    assert len(body["question_bank"]) == 1
    assert body["question_bank"][0]["id"]
    template_id = body["id"]

    listed = client.get("/api/templates", headers=staff_headers).json()
    summary = next(item for item in listed if item["id"] == template_id)
    assert summary["round_count"] == 2
    assert summary["question_count"] == 1
    assert summary["proctoring_mode"] == "strict"
    assert "question_bank" not in summary

    detail = client.get(f"/api/templates/{template_id}", headers=staff_headers)
    assert detail.status_code == 200
    assert detail.json()["description"] == "Standard backend first round"

    updated = client.patch(
        f"/api/templates/{template_id}",
        headers=staff_headers,
        json={"question_bank": [{"text": "Design a rate limiter.", "topic": "design"}]},
    )
    assert updated.status_code == 200
    assert [q["text"] for q in updated.json()["question_bank"]] == ["Design a rate limiter."]

    assert client.delete(f"/api/templates/{template_id}", headers=staff_headers).status_code == 204
    assert client.get(f"/api/templates/{template_id}", headers=staff_headers).status_code == 404


def test_clear_question_bank_with_null(client: TestClient, staff_headers: dict) -> None:
    template_id = _create_template(client, staff_headers)["id"]
    updated = client.patch(
        f"/api/templates/{template_id}", headers=staff_headers, json={"question_bank": None}
    )
    assert updated.status_code == 200
    assert updated.json()["question_bank"] == []


def test_attached_template_cannot_be_deleted(client: TestClient, staff_headers: dict) -> None:
    template_id = _create_template(client, staff_headers)["id"]
    job = client.post(
        "/api/jobs",
        headers=staff_headers,
        json={"title": "Backend Engineer", "template_id": template_id},
    )
    assert job.status_code == 201, job.text

    blocked = client.delete(f"/api/templates/{template_id}", headers=staff_headers)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "conflict"


def test_templates_are_isolated_between_users(client: TestClient, staff_headers: dict) -> None:
    template_id = _create_template(client, staff_headers)["id"]
    other = _login(client, make_user("other.templates@example.com", role="recruiter"))
    assert client.get(f"/api/templates/{template_id}", headers=other).status_code == 404
    assert client.get("/api/templates", headers=other).json() == []


def test_preview_generates_a_question(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    template_id = _create_template(client, staff_headers)["id"]

    async def fake(prompt: str, schema, **kwargs: object):
        assert "Backend Screen" in prompt
        return schema(question="What is a database index?", topic="databases")

    monkeypatch.setattr(PREVIEW_LLM, fake)

    response = client.post(
        f"/api/templates/{template_id}/preview", headers=staff_headers, json={}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question"] == "What is a database index?"
    assert body["topic"] == "databases"
    assert body["interview_type"] == "technical"
    assert body["difficulty"] == "intermediate"


def test_preview_round_override_selects_difficulty(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    template_id = _create_template(client, staff_headers)["id"]

    async def fake(prompt: str, schema, **kwargs: object):
        return schema(question="Implement a cache.", topic="design")

    monkeypatch.setattr(PREVIEW_LLM, fake)

    response = client.post(
        f"/api/templates/{template_id}/preview",
        headers=staff_headers,
        json={"round_key": "coding", "role": "Staff Engineer"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["difficulty"] == "advanced"


def test_preview_unknown_template_is_404(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    async def fake(prompt: str, schema, **kwargs: object):  # pragma: no cover
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(PREVIEW_LLM, fake)
    response = client.post("/api/templates/nope/preview", headers=staff_headers, json={})
    assert response.status_code == 404


def test_preview_unknown_round_is_404(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    template_id = _create_template(client, staff_headers)["id"]

    async def fake(prompt: str, schema, **kwargs: object):  # pragma: no cover
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(PREVIEW_LLM, fake)
    response = client.post(
        f"/api/templates/{template_id}/preview",
        headers=staff_headers,
        json={"round_key": "does-not-exist"},
    )
    assert response.status_code == 404


def test_preview_reports_service_unavailable(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    template_id = _create_template(client, staff_headers)["id"]

    async def boom(prompt: str, schema, **kwargs: object):
        raise RuntimeError("provider down")

    monkeypatch.setattr(PREVIEW_LLM, boom)
    response = client.post(
        f"/api/templates/{template_id}/preview", headers=staff_headers, json={}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
