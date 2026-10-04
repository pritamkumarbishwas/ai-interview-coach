import pytest
from fastapi.testclient import TestClient

from tests.test_resumes import RESUME_SERVICE_LLM, make_pdf

INTERVIEW_LLM = "app.services.interview_service.llm_service.generate_structured"


async def fake_resume_extraction(prompt: str, schema, **kwargs):
    return schema(skills=["Python", "FastAPI"], experience=[], projects=[], education=[])


async def fake_jd_extraction(prompt: str, schema, **kwargs):
    return schema(
        role_title="Backend Engineer",
        required_skills=["FastAPI"],
        responsibilities=["Build APIs"],
    )


async def fake_question_generation(prompt: str, schema, **kwargs):
    return schema(question="Explain how you would design a scalable REST API.")


async def fake_llm(prompt: str, schema, **kwargs):
    """Dispatcher for the shared `llm_service` singleton.

    Resume/JD/interview generation all go through one object, so a single
    patched method must answer every schema the flow uses.
    """
    builders = {
        "ResumeStructuredData": fake_resume_extraction,
        "JobDescriptionStructuredData": fake_jd_extraction,
        "QuestionGeneration": fake_question_generation,
    }
    builder = builders.get(schema.__name__)
    assert builder is not None, f"unexpected schema {schema.__name__}"
    return await builder(prompt, schema, **kwargs)


@pytest.fixture()
def interview_context(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> dict:
    """A resume and a job description owned by the authenticated user."""
    monkeypatch.setattr(RESUME_SERVICE_LLM, fake_llm)

    resume = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", make_pdf(), "application/pdf")},
    )
    assert resume.status_code == 201, resume.text

    jd = client.post(
        "/api/job-descriptions",
        headers=auth_headers,
        json={
            "title": "Backend Engineer",
            "company": "Acme",
            "raw_text": "Own our FastAPI services and MongoDB collections end to end.",
        },
    )
    assert jd.status_code == 201, jd.text
    return {"resume_id": resume.json()["id"], "jd_id": jd.json()["id"]}


def interview_payload(context: dict, **overrides) -> dict:
    payload = {
        "resume_id": context["resume_id"],
        "jd_id": context["jd_id"],
        "role": "Backend Engineer",
        "level": "mid",
        "type": "technical",
        "difficulty": "intermediate",
    }
    payload.update(overrides)
    return payload


def test_interview_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/interviews").status_code == 401
    assert client.post("/api/interviews", json={}).status_code == 401


def test_create_interview_returns_created_state(
    client: TestClient, auth_headers: dict, interview_context: dict
) -> None:
    response = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "created"
    assert body["role"] == "Backend Engineer"
    assert body["type"] == "technical"
    assert body["difficulty"] == "intermediate"
    assert body["questions"] == []
    assert body["started_at"] is None


def test_create_interview_rejects_unknown_resume(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/interviews",
        headers=auth_headers,
        json=interview_payload({"resume_id": "nope", "jd_id": "nope"}),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found"


def test_create_interview_allows_missing_resume(
    client: TestClient, auth_headers: dict, interview_context: dict
) -> None:
    payload = interview_payload(interview_context)
    payload.pop("resume_id")
    response = client.post("/api/interviews", headers=auth_headers, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["resume_id"] == ""
    assert body["status"] == "created"


def test_create_interview_rejects_invalid_type(
    client: TestClient, auth_headers: dict, interview_context: dict
) -> None:
    response = client.post(
        "/api/interviews",
        headers=auth_headers,
        json=interview_payload(interview_context, type="banana"),
    )
    assert response.status_code == 422


def test_list_and_get_interview(
    client: TestClient, auth_headers: dict, interview_context: dict
) -> None:
    created = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    ).json()

    listed = client.get("/api/interviews", headers=auth_headers)
    assert listed.status_code == 200
    summaries = listed.json()
    match = next(item for item in summaries if item["id"] == created["id"])
    assert match["question_count"] == 0
    # The list projection never ships the question texts.
    assert "questions" not in match

    detail = client.get(f"/api/interviews/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]


def test_get_unknown_interview_is_404(client: TestClient, auth_headers: dict) -> None:
    assert client.get("/api/interviews/not-an-id", headers=auth_headers).status_code == 404


def test_start_generates_first_question_and_current_question_is_stable(
    client: TestClient,
    auth_headers: dict,
    interview_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def counting_generation(prompt: str, schema, **kwargs):
        nonlocal calls
        calls += 1
        return schema(question="How does database indexing improve query performance?")

    monkeypatch.setattr(INTERVIEW_LLM, counting_generation)

    interview = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    ).json()

    started = client.post(f"/api/interviews/{interview['id']}/start", headers=auth_headers)
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "in_progress"
    assert body["question_number"] == 1
    assert body["total_asked"] == 1
    first_text = body["question"]["text"]

    # Reading the current question must not generate a second one.
    current = client.get(
        f"/api/interviews/{interview['id']}/current-question", headers=auth_headers
    )
    assert current.status_code == 200, current.text
    assert current.json()["question"]["text"] == first_text
    assert current.json()["question_number"] == 1
    assert calls == 1

    # The detail endpoint reflects the state machine transition.
    detail = client.get(f"/api/interviews/{interview['id']}", headers=auth_headers).json()
    assert detail["status"] == "in_progress"
    assert detail["started_at"] is not None
    assert len(detail["questions"]) == 1


def test_start_twice_is_a_conflict(
    client: TestClient,
    auth_headers: dict,
    interview_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(INTERVIEW_LLM, fake_question_generation)
    interview = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    ).json()

    first = client.post(f"/api/interviews/{interview['id']}/start", headers=auth_headers)
    assert first.status_code == 200
    second = client.post(f"/api/interviews/{interview['id']}/start", headers=auth_headers)
    assert second.status_code == 409
    assert second.json()["code"] == "conflict"


def test_start_interview_without_resume(
    client: TestClient,
    auth_headers: dict,
    interview_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A resume-less interview must still generate its first question."""
    monkeypatch.setattr(INTERVIEW_LLM, fake_question_generation)
    payload = interview_payload(interview_context)
    payload.pop("resume_id")
    created = client.post("/api/interviews", headers=auth_headers, json=payload)
    assert created.status_code == 201, created.text

    started = client.post(f"/api/interviews/{created.json()['id']}/start", headers=auth_headers)
    assert started.status_code == 200, started.text
    assert started.json()["question"]["text"]


def test_current_question_before_start_is_a_conflict(
    client: TestClient, auth_headers: dict, interview_context: dict
) -> None:
    interview = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    ).json()
    response = client.get(
        f"/api/interviews/{interview['id']}/current-question", headers=auth_headers
    )
    assert response.status_code == 409
    assert "not been started" in response.json()["detail"]


def test_start_leaves_interview_created_when_llm_is_down(
    client: TestClient,
    auth_headers: dict,
    interview_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(prompt: str, schema, **kwargs):
        raise RuntimeError("llm is down")

    monkeypatch.setattr(INTERVIEW_LLM, boom)
    interview = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    ).json()

    response = client.post(f"/api/interviews/{interview['id']}/start", headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"

    # The failed start must not burn the state transition: it can be retried.
    detail = client.get(f"/api/interviews/{interview['id']}", headers=auth_headers).json()
    assert detail["status"] == "created"
    assert detail["questions"] == []


def test_start_interview_of_another_user_is_404(
    client: TestClient,
    auth_headers: dict,
    interview_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(INTERVIEW_LLM, fake_question_generation)
    interview = client.post(
        "/api/interviews", headers=auth_headers, json=interview_payload(interview_context)
    ).json()

    register = client.post(
        "/api/auth/register",
        json={
            "name": "Other",
            "email": "other.interview@example.com",
            "password": "strongpassword1",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "other.interview@example.com", "password": "strongpassword1"},
    )
    assert register.status_code == 201
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get(f"/api/interviews/{interview['id']}", headers=other).status_code == 404
    assert client.post(f"/api/interviews/{interview['id']}/start", headers=other).status_code == 404
    assert (
        client.get(f"/api/interviews/{interview['id']}/current-question", headers=other).status_code
        == 404
    )
