from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from tests.test_resumes import RESUME_SERVICE_LLM, make_pdf

INTERVIEW_LLM = "app.services.interview_service.llm_service.generate_structured"

ANSWER = "I would add a B-tree index on the foreign key and verify with EXPLAIN."


@dataclass
class Env:
    setup: object  # callable(target: int) -> dict
    prompts: list[str] = field(default_factory=list)
    dispatcher: object = None


@pytest.fixture()
def env(client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch) -> Env:
    """Shared LLM dispatcher plus a helper that creates a started interview."""
    prompts: list[str] = []
    question_calls = 0

    async def dispatcher(prompt: str, schema, **kwargs):
        nonlocal question_calls
        prompts.append(prompt)
        name = schema.__name__
        if name == "ResumeStructuredData":
            return schema(skills=["Python", "FastAPI"], experience=[], projects=[], education=[])
        if name == "JobDescriptionStructuredData":
            return schema(
                role_title="Backend Engineer",
                required_skills=["FastAPI"],
                responsibilities=["Build APIs"],
            )
        if name == "QuestionGeneration":
            question_calls += 1
            return schema(
                question=f"Question number {question_calls}?",
                topic=f"topic-{question_calls}",
            )
        if name == "EvaluationGeneration":
            return schema(
                scores={
                    "technical": 80,
                    "relevance": 85,
                    "completeness": 70,
                    "structure": 75,
                    "clarity": 90,
                },
                strengths=["clear reasoning"],
                weaknesses=["missed edge cases"],
                feedback="Solid answer; cover failure modes next time.",
                improved_answer="A model answer.",
                next_step="new_topic",
            )
        raise AssertionError(f"unexpected schema {name}")

    monkeypatch.setattr(RESUME_SERVICE_LLM, dispatcher)

    def setup(target: int = 3) -> dict:
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
                "raw_text": "Own our FastAPI services and MongoDB collections.",
            },
        )
        assert jd.status_code == 201, jd.text
        created = client.post(
            "/api/interviews",
            headers=auth_headers,
            json={
                "resume_id": resume.json()["id"],
                "jd_id": jd.json()["id"],
                "role": "Backend Engineer",
                "level": "mid",
                "type": "technical",
                "difficulty": "intermediate",
                "target_questions": target,
            },
        )
        assert created.status_code == 201, created.text
        started = client.post(f"/api/interviews/{created.json()['id']}/start", headers=auth_headers)
        assert started.status_code == 200, started.text
        return {
            "id": created.json()["id"],
            "question_id": started.json()["question"]["id"],
            "target": target,
        }

    return Env(setup=setup, prompts=prompts, dispatcher=dispatcher)


def answer(client: TestClient, headers: dict, question_id: str, text: str = ANSWER):
    return client.post(
        f"/api/questions/{question_id}/answer", headers=headers, json={"answer": text}
    )


def test_answer_requires_auth(client: TestClient) -> None:
    assert client.post("/api/questions/abc/answer", json={"answer": "hi"}).status_code == 401


def test_answer_with_empty_text_is_rejected(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    response = answer(client, auth_headers, ctx["question_id"], text="")
    assert response.status_code == 422


def test_answer_unknown_question_is_404(client: TestClient, auth_headers: dict) -> None:
    response = answer(client, auth_headers, "not-a-question")
    assert response.status_code == 404
    assert response.json()["detail"] == "Question not found"


def test_answer_returns_evaluation_and_next_question(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=3)
    response = answer(client, auth_headers, ctx["question_id"])
    assert response.status_code == 200, response.text
    body = response.json()

    evaluation = body["evaluation"]
    scores = evaluation["scores"]
    assert set(scores) == {"technical", "relevance", "completeness", "structure", "clarity"}
    assert all(0 <= value <= 100 for value in scores.values())
    assert evaluation["overall"] == round(sum(scores.values()) / 5)
    assert evaluation["strengths"] == ["clear reasoning"]
    assert evaluation["weaknesses"] == ["missed edge cases"]
    assert evaluation["feedback"]
    assert evaluation["improved_answer"]
    assert evaluation["next_step"] == "new_topic"

    assert body["status"] == "in_progress"
    assert body["questions_answered"] == 1
    assert body["target_questions"] == 3
    assert body["next_question"]["sequence"] == 2
    assert body["next_question"]["topic"] == "topic-2"

    # The detail view carries the stored answers/evaluations.
    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert len(detail["answers"]) == 1
    assert detail["answers"][0]["question_id"] == ctx["question_id"]
    assert detail["answers"][0]["evaluation"]["overall"] == 80


def test_list_shows_progress_counts(client: TestClient, auth_headers: dict, env: Env) -> None:
    ctx = env.setup(target=3)
    answer(client, auth_headers, ctx["question_id"])
    summaries = client.get("/api/interviews", headers=auth_headers).json()
    item = next(s for s in summaries if s["id"] == ctx["id"])
    assert item["answered_count"] == 1
    assert item["target_questions"] == 3
    assert item["question_count"] == 2  # first + generated follow-up


def test_interview_completes_after_target_answers(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=2)

    first = answer(client, auth_headers, ctx["question_id"]).json()
    assert first["status"] == "in_progress"
    assert first["next_question"] is not None

    second = answer(client, auth_headers, first["next_question"]["id"])
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["status"] == "completed"
    assert body["next_question"] is None
    assert body["questions_answered"] == 2

    # A completed interview rejects everything.
    again = answer(client, auth_headers, first["next_question"]["id"])
    assert again.status_code == 409
    assert "completed" in again.json()["detail"]
    current = client.get(f"/api/interviews/{ctx['id']}/current-question", headers=auth_headers)
    assert current.status_code == 409
    restart = client.post(f"/api/interviews/{ctx['id']}/start", headers=auth_headers)
    assert restart.status_code == 409

    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert detail["completed_at"] is not None


def test_only_the_current_question_can_be_answered(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=3)
    first = answer(client, auth_headers, ctx["question_id"]).json()
    assert first["next_question"] is not None

    stale = answer(client, auth_headers, ctx["question_id"])
    assert stale.status_code == 409
    assert "current question" in stale.json()["detail"]


def test_evaluation_failure_saves_nothing(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(prompt: str, schema, **kwargs):
        raise RuntimeError("llm is down")

    ctx = env.setup()
    monkeypatch.setattr(INTERVIEW_LLM, boom)

    response = answer(client, auth_headers, ctx["question_id"])
    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"

    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert detail["answers"] == []
    assert detail["status"] == "in_progress"


def test_next_question_failure_saves_nothing(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_generation_only(prompt: str, schema, **kwargs):
        if schema.__name__ == "QuestionGeneration" and "next_step_decision" in prompt:
            raise RuntimeError("generation down")
        return await env.dispatcher(prompt, schema, **kwargs)

    ctx = env.setup()
    monkeypatch.setattr(INTERVIEW_LLM, fail_generation_only)

    response = answer(client, auth_headers, ctx["question_id"])
    assert response.status_code == 503

    # The answer and evaluation must not be half-recorded: the client can retry.
    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert detail["answers"] == []

    # Retrying with the LLM healthy again succeeds.
    monkeypatch.setattr(INTERVIEW_LLM, env.dispatcher)
    retry = answer(client, auth_headers, ctx["question_id"])
    assert retry.status_code == 200, retry.text


def test_decision_and_covered_topics_reach_the_next_question_prompt(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def follow_up_instead(prompt: str, schema, **kwargs):
        result = await env.dispatcher(prompt, schema, **kwargs)
        if schema.__name__ == "EvaluationGeneration":
            result.next_step = "follow_up"
        return result

    monkeypatch.setattr(INTERVIEW_LLM, follow_up_instead)
    ctx = env.setup(target=3)
    answer(client, auth_headers, ctx["question_id"])

    next_prompt = next(p for p in env.prompts if "next_step_decision" in p)
    assert "<next_step_decision>" in next_prompt
    assert "\nfollow_up" in next_prompt
    assert "topic-1" in next_prompt  # covered topics include the first question
    assert "Question number 1?" in next_prompt


def test_answer_of_another_users_question_is_404(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    register = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other.answer@example.com", "password": "strongpassword1"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "other.answer@example.com", "password": "strongpassword1"},
    )
    assert register.status_code == 201
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = answer(client, other, ctx["question_id"])
    assert response.status_code == 404
