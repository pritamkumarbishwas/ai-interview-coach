"""Phase 6: rubric-based, evidence-cited, advisory competency scorecard."""

from fastapi.testclient import TestClient

from app.models.answer import Answer, Evaluation, ScoreBreakdown
from app.models.interview import Interview, Question
from app.services.scorecard_service import ScorecardService

INTERVIEW_LLM = "app.services.interview_service.llm_service.generate_structured"
CANDIDATE_NAME = "Grace Hopper"
CANDIDATE_EMAIL = "grace@example.com"


def _scores(value: int) -> ScoreBreakdown:
    return ScoreBreakdown(
        technical=value, relevance=value, completeness=value, structure=value, clarity=value
    )


def _answer(
    question_id: str, *, overall: int, competency: str, evidence: list[str] | None = None
) -> Answer:
    return Answer(
        id=f"a-{question_id}",
        question_id=question_id,
        text="answer text",
        evaluation=Evaluation(
            scores=_scores(overall),
            overall=overall,
            competency=competency,
            evidence=evidence or [],
        ),
    )


def test_build_aggregates_competencies_with_evidence() -> None:
    interview = Interview(
        id="i1",
        user_id="u1",
        resume_id="",
        jd_id="j1",
        role="Backend Engineer",
        rubric=["SQL", "Communication"],
        pass_threshold=70,
        questions=[
            Question(id="q1", sequence=1, text="Indexes?", topic="databases"),
            Question(id="q2", sequence=2, text="Sharding?", topic="databases"),
            Question(id="q3", sequence=3, text="Design a queue?", topic="system design"),
        ],
        answers=[
            _answer("q1", overall=80, competency="SQL", evidence=["used a covering index"]),
            _answer("q2", overall=60, competency="SQL", evidence=["relied on full scans"]),
            # Empty competency falls back to the question's topic.
            _answer("q3", overall=90, competency=""),
        ],
    )

    card = ScorecardService().build(interview)

    assert card.advisory is True
    assert card.identity_hidden is True

    by_name = {item.competency: item for item in card.competencies}
    # An un-scored rubric dimension still shows up (so reviewers see the gap).
    assert by_name["Communication"].score == 0.0
    assert by_name["Communication"].answered == 0
    assert by_name["SQL"].score == 70.0
    assert by_name["SQL"].answered == 2
    assert by_name["system design"].score == 90.0

    sql_evidence = by_name["SQL"].evidence
    assert [entry.quotes for entry in sql_evidence] == [
        ["used a covering index"],
        ["relied on full scans"],
    ]

    # Overall averages the competency means (unanswered dimensions excluded).
    assert card.overall_score == 80.0
    assert card.strengths == ["SQL", "system design"]
    assert card.concerns == []
    assert card.threshold == 70.0
    assert card.meets_threshold is True
    assert "threshold" in card.recommendation


def test_threshold_advisory_when_not_met() -> None:
    interview = Interview(
        id="i2",
        user_id="u1",
        resume_id="",
        jd_id="j1",
        role="Engineer",
        pass_threshold=80,
        questions=[Question(id="q1", sequence=1, text="?", topic="databases")],
        answers=[_answer("q1", overall=40, competency="SQL")],
    )
    card = ScorecardService().build(interview)
    assert card.meets_threshold is False
    assert card.overall_score == 40.0
    assert card.concerns == ["SQL"]
    assert "Below the round threshold" in card.recommendation


def test_no_threshold_is_advisory_only() -> None:
    interview = Interview(
        id="i3",
        user_id="u1",
        resume_id="",
        jd_id="j1",
        role="Engineer",
        questions=[Question(id="q1", sequence=1, text="?", topic="databases")],
        answers=[_answer("q1", overall=55, competency="SQL")],
    )
    card = ScorecardService().build(interview)
    assert card.threshold == 0.0
    assert card.meets_threshold is False
    assert "no pass threshold" in card.recommendation


def _patch_llm(monkeypatch, prompts: list[str]) -> None:
    state = {"n": 0}

    async def fake(prompt: str, schema, **kwargs: object):
        prompts.append(prompt)
        name = schema.__name__
        if name == "QuestionGeneration":
            state["n"] += 1
            return schema(question=f"Question {state['n']}?", topic=f"topic-{state['n']}")
        if name == "EvaluationGeneration":
            return schema(
                scores=dict.fromkeys(
                    ["technical", "relevance", "completeness", "structure", "clarity"], 72
                ),
                strengths=["clear"],
                weaknesses=[],
                feedback="ok",
                improved_answer="model answer",
                next_step="new_topic",
                competency="Problem Solving",
                evidence=["I profiled the hot path"],
            )
        if name == "ReportGeneration":
            return schema(
                narrative="ok",
                preparation_plan=[{"focus": "Depth", "actions": ["Practice out loud"]}],
            )
        raise AssertionError(f"unexpected schema {name}")

    monkeypatch.setattr(INTERVIEW_LLM, fake)


def _job_with_rubric(client: TestClient, headers: dict, target: int = 2) -> str:
    template = client.post(
        "/api/templates",
        headers=headers,
        json={
            "name": "Screening",
            "config": {
                "proctoring_mode": "off",
                "rounds": [
                    {
                        "key": "screen",
                        "interview_type": "technical",
                        "difficulty": "intermediate",
                        "duration_minutes": 30,
                        "target_questions": target,
                        "response_modes": ["typed"],
                        "rubric": ["Problem Solving", "Communication"],
                        "pass_threshold": 70,
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


def _run_candidate_flow(client: TestClient, token: str) -> None:
    started = client.post(f"/api/screening/{token}/start", json={"consent": False})
    assert started.status_code == 200, started.text
    question_id = started.json()["question"]["id"]
    for _ in range(2):
        answered = client.post(
            f"/api/screening/{token}/questions/{question_id}/answer",
            json={"answer": "I would profile first, then fix the bottleneck."},
        )
        assert answered.status_code == 200, answered.text
        if answered.json()["status"] == "completed":
            return
        question_id = answered.json()["next_question"]["id"]
    raise AssertionError("candidate flow did not complete")


def test_scorecard_endpoint_scores_a_completed_round(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    prompts: list[str] = []
    _patch_llm(monkeypatch, prompts)
    job_id = _job_with_rubric(client, staff_headers)

    invitation = client.post(
        "/api/invitations",
        headers=staff_headers,
        json={
            "job_id": job_id,
            "candidate_email": CANDIDATE_EMAIL,
            "candidate_name": CANDIDATE_NAME,
        },
    ).json()
    token = invitation["accept_url"].split("/interview/", 1)[1]
    _run_candidate_flow(client, token)

    response = client.get(
        f"/api/invitations/{invitation['id']}/scorecard", headers=staff_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["advisory"] is True
    assert body["identity_hidden"] is True
    assert body["overall_score"] == 72.0
    assert body["meets_threshold"] is True
    by_name = {item["competency"]: item for item in body["competencies"]}
    assert by_name["Problem Solving"]["score"] == 72.0
    assert by_name["Problem Solving"]["evidence"][0]["quotes"] == ["I profiled the hot path"]
    assert by_name["Communication"]["answered"] == 0

    # Bias guardrail: identity is never an input to the scoring prompts.
    joined = " ".join(prompts)
    assert CANDIDATE_NAME not in joined
    assert CANDIDATE_EMAIL not in joined


def test_scorecard_access_control(
    client: TestClient, staff_headers: dict, auth_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    invitation = client.post(
        "/api/invitations",
        headers=staff_headers,
        json={"job_id": job_id, "candidate_email": CANDIDATE_EMAIL},
    ).json()
    url = f"/api/invitations/{invitation['id']}/scorecard"

    # Not started yet -> conflict.
    assert client.get(url, headers=staff_headers).status_code == 409
    # Candidates cannot read the scorecard.
    assert client.get(url, headers=auth_headers).status_code == 403
    # Unknown invitation -> 404.
    assert (
        client.get(
            "/api/invitations/64b000000000000000000000/scorecard", headers=staff_headers
        ).status_code
        == 404
    )
