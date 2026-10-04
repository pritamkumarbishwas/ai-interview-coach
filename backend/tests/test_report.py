import pytest
from fastapi.testclient import TestClient

from app.models.answer import Answer, Evaluation, ScoreBreakdown
from app.models.interview import Interview, Question
from app.prompts.templates import MAX_REPORT_CONTEXT_CHARS
from app.services.interview_service import (
    _context_block,
    _performance_payload,
    aggregate_scores,
)
from tests.conftest import INTERVIEW_LLM, Env
from tests.test_answers import answer


def get_report(client: TestClient, headers: dict, interview_id: str):
    return client.get(f"/api/interviews/{interview_id}/report", headers=headers)


def complete_interview(client: TestClient, headers: dict, ctx: dict) -> dict:
    """Answer questions until the interview completes; return the last body."""
    question_id = ctx["question_id"]
    for _ in range(ctx["target"] + 1):
        response = answer(client, headers, question_id)
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] == "completed":
            return body
        assert body["next_question"] is not None, body
        question_id = body["next_question"]["id"]
    raise AssertionError("interview did not complete")


def report_prompts(env: Env) -> list[str]:
    return [prompt for prompt in env.prompts if "<performance_data>" in prompt]


def test_report_requires_auth(client: TestClient) -> None:
    assert client.get("/api/interviews/abc/report").status_code == 401


def test_report_before_completion_is_a_conflict(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=3)
    response = get_report(client, auth_headers, ctx["id"])
    assert response.status_code == 409
    assert "completed" in response.json()["detail"]


def test_report_is_generated_on_completion_and_cached(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=2)
    final = complete_interview(client, auth_headers, ctx)
    assert final["status"] == "completed"
    assert len(report_prompts(env)) == 1  # generated once, at completion

    response = get_report(client, auth_headers, ctx["id"])
    assert response.status_code == 200, response.text
    body = response.json()

    # Numbers are aggregated in code from the stored evaluations:
    # every answer scores (80, 85, 70, 75, 90) -> overall 80, comm (75+90)/2.
    assert body["interview_id"] == ctx["id"]
    assert body["overall_score"] == 80.0
    assert body["technical_score"] == 80.0
    assert body["communication_score"] == 82.5
    assert body["strong_topics"] == ["topic-1", "topic-2"]  # 80 >= 70
    assert body["weak_topics"] == []
    assert body["topics_to_study"] == []
    assert body["narrative"]
    assert body["preparation_plan"][0]["focus"] == "Failure modes"
    assert body["preparation_plan"][0]["actions"]
    assert body["generated_at"] is not None

    # Cached: a second read returns the same report without another LLM call.
    again = get_report(client, auth_headers, ctx["id"])
    assert again.status_code == 200
    assert again.json() == body
    assert len(report_prompts(env)) == 1


def test_strong_and_weak_topics_follow_the_scores(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    eval_calls = 0

    async def first_high_second_low(prompt: str, schema, **kwargs):
        nonlocal eval_calls
        result = await env.dispatcher(prompt, schema, **kwargs)
        if schema.__name__ == "EvaluationGeneration":
            eval_calls += 1
            value = 90 if eval_calls == 1 else 30
            result.scores = ScoreBreakdown(
                technical=value,
                relevance=value,
                completeness=value,
                structure=value,
                clarity=value,
            )
        return result

    monkeypatch.setattr(INTERVIEW_LLM, first_high_second_low)
    ctx = env.setup(target=2)
    complete_interview(client, auth_headers, ctx)

    body = get_report(client, auth_headers, ctx["id"]).json()
    assert body["overall_score"] == 60.0  # mean(90, 30)
    assert body["technical_score"] == 60.0
    assert body["communication_score"] == 60.0
    assert body["strong_topics"] == ["topic-1"]
    assert body["weak_topics"] == ["topic-2"]
    assert body["topics_to_study"] == ["topic-2"]


def test_report_backfills_when_completion_generation_fails(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def flaky_report(prompt: str, schema, **kwargs):
        nonlocal calls
        if schema.__name__ == "ReportGeneration":
            calls += 1
            if calls == 1:
                raise RuntimeError("report hiccup")
        return await env.dispatcher(prompt, schema, **kwargs)

    monkeypatch.setattr(INTERVIEW_LLM, flaky_report)
    ctx = env.setup(target=2)

    # The failed report must not block completion of the interview.
    final = complete_interview(client, auth_headers, ctx)
    assert final["status"] == "completed"

    response = get_report(client, auth_headers, ctx["id"])
    assert response.status_code == 200, response.text
    assert response.json()["narrative"]
    assert calls == 2  # one failure at completion, one success on read

    assert get_report(client, auth_headers, ctx["id"]).status_code == 200
    assert calls == 2  # backfill is cached


def test_report_generation_failure_returns_503_then_recovers(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def report_down(prompt: str, schema, **kwargs):
        if schema.__name__ == "ReportGeneration":
            raise RuntimeError("report down")
        return await env.dispatcher(prompt, schema, **kwargs)

    monkeypatch.setattr(INTERVIEW_LLM, report_down)
    ctx = env.setup(target=2)
    complete_interview(client, auth_headers, ctx)

    failed = get_report(client, auth_headers, ctx["id"])
    assert failed.status_code == 503
    assert failed.json()["code"] == "service_unavailable"

    # Nothing half-cached: a healthy LLM generates the report on retry.
    monkeypatch.setattr(INTERVIEW_LLM, env.dispatcher)
    recovered = get_report(client, auth_headers, ctx["id"])
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["narrative"]


def test_whitespace_only_narrative_is_rejected(
    client: TestClient, auth_headers: dict, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def blank_narrative(prompt: str, schema, **kwargs):
        result = await env.dispatcher(prompt, schema, **kwargs)
        if schema.__name__ == "ReportGeneration":
            result.narrative = "   "
        return result

    monkeypatch.setattr(INTERVIEW_LLM, blank_narrative)
    ctx = env.setup(target=2)
    final = complete_interview(client, auth_headers, ctx)
    assert final["status"] == "completed"  # blank report never blocks completion

    response = get_report(client, auth_headers, ctx["id"])
    assert response.status_code == 503
    assert "empty report" in response.json()["detail"]


def test_report_of_another_users_interview_is_404(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup(target=1)
    complete_interview(client, auth_headers, ctx)

    register = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other.report@example.com", "password": "strongpassword1"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "other.report@example.com", "password": "strongpassword1"},
    )
    assert register.status_code == 201
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert get_report(client, other, ctx["id"]).status_code == 404


def _scored_answer(question_id: str, score: int) -> Answer:
    breakdown = ScoreBreakdown(
        technical=score, relevance=score, completeness=score, structure=score, clarity=score
    )
    return Answer(
        id=f"a-{question_id}",
        question_id=question_id,
        text="x",
        evaluation=Evaluation(scores=breakdown, overall=breakdown.overall),
    )


def test_aggregate_scores_averages_evaluations_and_buckets_topics() -> None:
    interview = Interview(
        user_id="u",
        resume_id="r",
        jd_id="j",
        role="Backend",
        questions=[
            Question(id="q1", sequence=1, text="?", topic="indexing"),
            Question(id="q2", sequence=2, text="?", topic="caching"),
            Question(id="q3", sequence=3, text="?", topic="networking"),
            Question(id="q4", sequence=4, text="?", topic="unanswered"),
        ],
        answers=[
            _scored_answer("q1", 70),  # exactly at the strong threshold
            _scored_answer("q2", 50),  # exactly at the weak threshold: neither
            _scored_answer("q3", 40),  # weak
        ],
    )
    aggregates = aggregate_scores(interview)
    assert aggregates.overall_score == 53.3  # (70 + 50 + 40) / 3
    assert aggregates.technical_score == 53.3
    assert aggregates.communication_score == 53.3
    assert aggregates.strong_topics == ["indexing"]
    assert aggregates.weak_topics == ["networking"]  # weakest first ordering


def test_aggregate_scores_of_an_empty_interview_is_zero() -> None:
    aggregates = aggregate_scores(Interview(user_id="u", resume_id="r", jd_id="j", role="Backend"))
    assert aggregates.overall_score == 0.0
    assert aggregates.technical_score == 0.0
    assert aggregates.communication_score == 0.0
    assert aggregates.strong_topics == []
    assert aggregates.weak_topics == []


def test_report_payload_stays_bounded_for_max_size_interviews() -> None:
    """20 answered questions with pathological LLM text must still fit."""
    questions = [
        Question(id=f"q{i}", sequence=i, text="Q" * 500, topic="T" * 200) for i in range(1, 21)
    ]
    breakdown = ScoreBreakdown(
        technical=50, relevance=50, completeness=50, structure=50, clarity=50
    )
    answers = [
        Answer(
            id=f"a-{question.id}",
            question_id=question.id,
            text="A" * 2_000,
            evaluation=Evaluation(
                scores=breakdown,
                overall=breakdown.overall,
                weaknesses=["W" * 400] * 6,
                feedback="F" * 800,
            ),
        )
        for question in questions
    ]
    interview = Interview(
        user_id="u",
        resume_id="r",
        jd_id="j",
        role="Backend",
        target_questions=20,
        questions=questions,
        answers=answers,
    )

    payload = _performance_payload(interview)
    for entry in payload["questions"]:
        assert len(entry["topic"]) <= 100
        assert len(entry["question"]) <= 160
        assert len(entry["feedback"]) <= 200
        assert len(entry["weaknesses"]) <= 3
        assert all(len(weakness) <= 150 for weakness in entry["weaknesses"])
    for key in ("strong_topics", "weak_topics", "topics_to_study"):
        assert all(len(topic) <= 100 for topic in payload[key])

    block = _context_block(payload, MAX_REPORT_CONTEXT_CHARS)
    assert len(block) <= MAX_REPORT_CONTEXT_CHARS + 3  # + "..." if trimmed
    assert block.endswith("}")  # never cut mid-JSON at this size
