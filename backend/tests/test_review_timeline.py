"""Phase 7: transcript ↔ recording timeline and recorder-anchored offsets."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.models.answer import Answer, Evaluation, ScoreBreakdown
from app.models.integrity import IntegrityMoment, IntegrityReport
from app.models.interview import (
    Interview,
    ProctoringEvent,
    ProctoringSession,
    Question,
    RecordingMeta,
)
from app.services.review_service import ReviewService

START = datetime(2026, 10, 18, 9, 0, 0)


def _scores(value: int) -> ScoreBreakdown:
    return ScoreBreakdown(
        technical=value, relevance=value, completeness=value, structure=value, clarity=value
    )


def _empty_integrity() -> IntegrityReport:
    return IntegrityReport(
        interview_id="i1",
        score=100,
        level="low",
        recording_available=True,
        recording_size_bytes=10,
    )


def _interview(**overrides: object) -> Interview:
    base: dict = {
        "id": "i1",
        "user_id": "guest1",
        "resume_id": "",
        "jd_id": "j1",
        "role": "Engineer",
        "questions": [Question(id="q1", sequence=1, text="Indexes?", topic="databases")],
        "answers": [
            Answer(
                id="a1",
                question_id="q1",
                text="Use a covering index.",
                created_at=START + timedelta(seconds=95),
                evaluation=Evaluation(
                    scores=_scores(80), overall=80, competency="SQL", evidence=["covering index"]
                ),
            )
        ],
        "recordings": {
            "camera": RecordingMeta(
                file_id="i1:camera",
                size_bytes=100,
                finalized=True,
                capture_started_at=START,
            )
        },
    }
    base.update(overrides)
    return Interview(**base)


def test_offsets_are_anchored_to_the_recorder_start() -> None:
    timeline = ReviewService().build(_interview(), _empty_integrity())
    assert timeline.anchored_to_recording is True
    (entry,) = timeline.entries
    assert entry.kind == "answer"
    assert entry.at_seconds == 95.0
    assert entry.score == 80
    assert entry.competency == "SQL"
    assert timeline.duration_seconds == 95.0


def test_signals_interleave_in_time_order() -> None:
    integrity = IntegrityReport(
        interview_id="i1",
        score=90,
        level="moderate",
        moments=[
            IntegrityMoment(
                at=START + timedelta(seconds=150),
                type="tab_blur",
                label="Tab lost focus",
                severity=6,
            )
        ],
    )
    timeline = ReviewService().build(_interview(), integrity)
    assert [entry.kind for entry in timeline.entries] == ["answer", "signal"]
    assert [entry.at_seconds for entry in timeline.entries] == [95.0, 150.0]
    assert timeline.entries[1].label == "Tab lost focus"


def test_falls_back_to_session_start_and_flags_it() -> None:
    interview = _interview(
        recordings={},
        proctoring_session=ProctoringSession(started_at=START, events=[ProctoringEvent(type="x")]),
    )
    timeline = ReviewService().build(interview, _empty_integrity())
    assert timeline.anchored_to_recording is False
    assert timeline.recording_available is False
    assert timeline.entries[0].at_seconds == 95.0


def test_clock_skew_never_produces_a_negative_offset() -> None:
    # Answer recorded "before" the anchor: clamp to zero rather than go negative.
    interview = _interview(
        answers=[
            Answer(
                id="a1",
                question_id="q1",
                text="early",
                created_at=START - timedelta(seconds=30),
            )
        ]
    )
    timeline = ReviewService().build(interview, _empty_integrity())
    assert timeline.entries[0].at_seconds == 0.0


def test_timeline_endpoint_requires_started_interview(
    client: TestClient, staff_headers: dict, auth_headers: dict, monkeypatch
) -> None:
    from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow
    from tests.test_shortlist import _invite

    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id, "timeline@example.com")
    url = f"/api/invitations/{invitation['id']}/timeline"

    assert client.get(url, headers=staff_headers).status_code == 409
    assert client.get(url, headers=auth_headers).status_code == 403

    token = invitation["accept_url"].split("/interview/", 1)[1]
    _run_candidate_flow(client, token)

    body = client.get(url, headers=staff_headers).json()
    assert body["interview_id"]
    assert [entry["kind"] for entry in body["entries"]] == ["answer"] * len(body["entries"])
    assert body["entries"][0]["answer"]


def test_recording_download_is_recruiter_only_and_404_when_missing(
    client: TestClient, staff_headers: dict, auth_headers: dict, monkeypatch
) -> None:
    from tests.test_shortlist import _invite
    from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow

    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id, "video@example.com")
    url = f"/api/invitations/{invitation['id']}/recordings/camera"
    token = invitation["accept_url"].split("/interview/", 1)[1]
    _run_candidate_flow(client, token)

    # Nothing was recorded in this flow, so the recording is absent (not a 500).
    assert client.get(url, headers=staff_headers).status_code == 404
    assert client.get(url, headers=auth_headers).status_code == 403


def test_recording_download_and_anchored_timeline_end_to_end(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    """A recorded, proctored session streams back and anchors the timeline."""
    from tests.test_screening import (
        _invite,
        _job_with_template,
        _patch_llm,
        _start,
        _token,
    )

    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="strict", target=2)
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    capture_started_at = datetime.now(UTC).isoformat()
    question_id = _start(client, token)

    chunk_url = f"/api/screening/{token}/recordings/chunk"
    first = client.post(
        chunk_url,
        data={
            "kind": "camera",
            "seq": "0",
            "finalize": "false",
            "content_type": "video/webm",
            # Only the first chunk reports the start; the service carries it.
            "capture_started_at": capture_started_at,
        },
        files={"chunk": ("0.webm", b"first-half-", "video/webm")},
    )
    assert first.status_code == 204, first.text

    client.post(
        f"/api/screening/{token}/proctoring/events",
        json={"type": "tab_blur", "details": {}},
    )

    # Answer both questions so the session (and recording) completes.
    answer = client.post(
        f"/api/screening/{token}/questions/{question_id}/answer",
        json={"answer": "Use a covering index."},
    )
    next_id = answer.json()["next_question"]["id"]
    client.post(
        f"/api/screening/{token}/questions/{next_id}/answer",
        json={"answer": "Measure with EXPLAIN."},
    )

    final = client.post(
        chunk_url,
        data={"kind": "camera", "seq": "1", "finalize": "true", "content_type": "video/webm"},
        files={"chunk": ("1.webm", b"second-half", "video/webm")},
    )
    assert final.status_code == 204, final.text

    download = client.get(
        f"/api/invitations/{invitation['id']}/recordings/camera", headers=staff_headers
    )
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("video/webm")
    assert download.content == b"first-half-second-half"

    body = client.get(
        f"/api/invitations/{invitation['id']}/timeline", headers=staff_headers
    ).json()
    assert body["recording_available"] is True
    assert body["anchored_to_recording"] is True

    kinds = [entry["kind"] for entry in body["entries"]]
    assert "answer" in kinds
    assert "signal" in kinds
    # Chronological, non-negative offsets (recorder start precedes answers).
    offsets = [entry["at_seconds"] for entry in body["entries"]]
    assert offsets == sorted(offsets)
    assert all(offset >= 0 for offset in offsets)
    assert body["duration_seconds"] >= offsets[-1]

