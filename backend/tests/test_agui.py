import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import INTERVIEW_LLM, Env

ANSWER = "I would add a B-tree index on the foreign key and verify with EXPLAIN."


@pytest.fixture()
def agui_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agui_enabled", True)


def payload(interview_id: str, question_id: str | None, text: str = ANSWER) -> dict:
    forwarded = {"question_id": question_id} if question_id is not None else {}
    return {
        "threadId": interview_id,
        "runId": "run-1",
        "messages": [{"id": "user-1", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": forwarded,
    }


def post(client: TestClient, headers: dict, interview_id: str, body: dict):
    return client.post(
        f"/api/agui/interviews/{interview_id}", headers=headers, json=body
    )


def events(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.iter_lines()
        if line.startswith("data: ")
    ]


def test_agui_requires_auth(client: TestClient) -> None:
    response = post(client, {}, "anything", payload("anything", "q"))
    assert response.status_code == 401


def test_agui_is_501_when_disabled(client: TestClient, auth_headers: dict) -> None:
    response = post(client, auth_headers, "anything", payload("anything", "q"))
    assert response.status_code == 501
    assert response.json()["code"] == "feature_unavailable"


def test_agui_streams_the_answer_turn(
    client: TestClient, auth_headers: dict, env: Env, agui_enabled: None
) -> None:
    ctx = env.setup(target=3)
    with client.stream(
        "POST",
        f"/api/agui/interviews/{ctx['id']}",
        headers=auth_headers,
        json=payload(ctx["id"], ctx["question_id"]),
    ) as response:
        assert response.status_code == 200, response.text
        streamed = events(response)

    assert [event["type"] for event in streamed] == [
        "RUN_STARTED",
        "STATE_SNAPSHOT",
        "STEP_STARTED",
        "STEP_FINISHED",
        "STATE_SNAPSHOT",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]
    assert streamed[1]["snapshot"]["answered_count"] == 0
    assert streamed[1]["snapshot"]["current_question_id"] == ctx["question_id"]
    after = streamed[4]["snapshot"]
    assert after["answered_count"] == 1
    assert after["current_question"]["sequence"] == 2
    assert "answers" not in after
    assert "evaluation" not in after
    assert streamed[6]["delta"] == "Question number 2?"
    assert streamed[-1]["result"]["status"] == "in_progress"
    assert streamed[-1]["result"]["questions_answered"] == 1

    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert len(detail["answers"]) == 1


def test_agui_rejects_a_stale_question_before_streaming(
    client: TestClient, auth_headers: dict, env: Env, agui_enabled: None
) -> None:
    ctx = env.setup(target=3)
    first = client.post(
        f"/api/questions/{ctx['question_id']}/answer",
        headers=auth_headers,
        json={"answer": ANSWER},
    )
    assert first.status_code == 200, first.text

    response = post(client, auth_headers, ctx["id"], payload(ctx["id"], ctx["question_id"]))
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/json")
    assert "current question" in response.json()["detail"]

    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert len(detail["answers"]) == 1


def test_agui_requires_the_question_id(
    client: TestClient, auth_headers: dict, env: Env, agui_enabled: None
) -> None:
    ctx = env.setup(target=3)
    response = post(client, auth_headers, ctx["id"], payload(ctx["id"], None))
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"


def test_agui_final_answer_completes_the_interview(
    client: TestClient, auth_headers: dict, env: Env, agui_enabled: None
) -> None:
    ctx = env.setup(target=2)
    first = client.post(
        f"/api/questions/{ctx['question_id']}/answer",
        headers=auth_headers,
        json={"answer": ANSWER},
    ).json()
    next_id = first["next_question"]["id"]

    with client.stream(
        "POST",
        f"/api/agui/interviews/{ctx['id']}",
        headers=auth_headers,
        json=payload(ctx["id"], next_id),
    ) as response:
        assert response.status_code == 200, response.text
        streamed = events(response)

    types = [event["type"] for event in streamed]
    assert types == [
        "RUN_STARTED",
        "STATE_SNAPSHOT",
        "STEP_STARTED",
        "STEP_FINISHED",
        "STATE_SNAPSHOT",
        "RUN_FINISHED",
    ]
    after = streamed[4]["snapshot"]
    assert after["completed"] is True
    assert after["current_question"] is None
    assert streamed[-1]["result"]["status"] == "completed"


def test_agui_failure_after_streaming_is_a_run_error(
    client: TestClient,
    auth_headers: dict,
    env: Env,
    agui_enabled: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_generation(prompt: str, schema, **kwargs):
        if schema.__name__ == "QuestionGeneration":
            raise RuntimeError("generation down")
        return await env.dispatcher(prompt, schema, **kwargs)

    ctx = env.setup(target=3)
    monkeypatch.setattr(INTERVIEW_LLM, fail_generation)

    with client.stream(
        "POST",
        f"/api/agui/interviews/{ctx['id']}",
        headers=auth_headers,
        json=payload(ctx["id"], ctx["question_id"]),
    ) as response:
        assert response.status_code == 200, response.text
        streamed = events(response)

    assert streamed[-1]["type"] == "RUN_ERROR"
    assert streamed[-1]["code"] == "service_unavailable"
    detail = client.get(f"/api/interviews/{ctx['id']}", headers=auth_headers).json()
    assert detail["answers"] == []
