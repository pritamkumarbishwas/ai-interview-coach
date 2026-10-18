"""Phase 4: guest recording, proctoring lifecycle, STT, and time extensions.

Extends the Phase 3 magic-link flow (`tests/test_screening.py`) with the
candidate-panel capabilities: token-addressed recording uploads, advisory
integrity signals, server-side transcription, and recruiter accommodations.
"""

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.transcription import NullTranscriber
from tests.conftest import _with_mongo
from tests.test_screening import (
    _invite,
    _job_with_template,
    _patch_llm,
    _set_invitation,
    _token,
)


def _read_invitation(invitation_id: str) -> dict:
    box: dict = {}

    async def run(db) -> None:
        doc = await db.screening_invitations.find_one({"_id": ObjectId(invitation_id)})
        box.update(doc or {})

    _with_mongo(run)
    return box


def _read_interview(interview_id: str) -> dict:
    box: dict = {}

    async def run(db) -> None:
        doc = await db.interviews.find_one({"_id": ObjectId(interview_id)})
        box.update(doc or {})

    _with_mongo(run)
    return box


def _start(client: TestClient, token: str, consent: bool = True) -> str:
    response = client.post(f"/api/screening/{token}/start", json={"consent": consent})
    assert response.status_code == 200, response.text
    return response.json()["question"]["id"]


def _interview_id(invitation_id: str) -> str:
    return _read_invitation(invitation_id)["interview_id"]


def test_proctoring_session_lifecycle(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="strict", target=2)
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    question_id = _start(client, token)

    active = _read_interview(_interview_id(invitation["id"]))["proctoring_session"]
    assert active["status"] == "active"
    assert active["started_at"] is not None
    assert active["consent_given_at"] is not None
    assert active["ended_at"] is None

    first = client.post(
        f"/api/screening/{token}/questions/{question_id}/answer",
        json={"answer": "Use an index to avoid a full collection scan."},
    )
    next_id = first.json()["next_question"]["id"]
    second = client.post(
        f"/api/screening/{token}/questions/{next_id}/answer",
        json={"answer": "Measure with EXPLAIN before and after."},
    )
    assert second.json()["status"] == "completed"

    ended = _read_interview(_interview_id(invitation["id"]))["proctoring_session"]
    assert ended["status"] == "completed"
    assert ended["ended_at"] is not None


def test_guest_recording_chunk_upload(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    _start(client, token, consent=False)

    endpoint = f"/api/screening/{token}/recordings/chunk"
    first = client.post(
        endpoint,
        data={"kind": "camera", "seq": "0", "finalize": "false", "content_type": "video/webm"},
        files={"chunk": ("0.webm", b"chunk-zero-bytes", "video/webm")},
    )
    assert first.status_code == 204, first.text

    final = client.post(
        endpoint,
        data={"kind": "camera", "seq": "1", "finalize": "true", "content_type": "video/webm"},
        files={"chunk": ("1.webm", b"more-bytes", "video/webm")},
    )
    assert final.status_code == 204, final.text

    meta = _read_interview(_interview_id(invitation["id"]))["recordings"]["camera"]
    assert meta["finalized"] is True
    assert meta["size_bytes"] >= len(b"chunk-zero-bytes") + len(b"more-bytes")


def test_guest_recording_rejects_bad_content_type(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    token = _token(_invite(client, staff_headers, job_id))
    _start(client, token, consent=False)

    bad = client.post(
        f"/api/screening/{token}/recordings/chunk",
        data={"kind": "camera", "seq": "0", "content_type": "application/pdf"},
        files={"chunk": ("0.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert bad.status_code == 415


def test_guest_proctoring_events(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="strict")
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    _start(client, token)

    for event_type in ("tab_blur", "camera_off"):
        response = client.post(
            f"/api/screening/{token}/proctoring/events",
            json={"type": event_type, "details": {"at": "now"}},
        )
        assert response.status_code == 204, response.text

    events = _read_interview(_interview_id(invitation["id"]))["proctoring_session"]["events"]
    assert [event["type"] for event in events] == ["tab_blur", "camera_off"]


def test_guest_endpoints_require_a_started_interview(
    client: TestClient, staff_headers: dict
) -> None:
    job_id = _job_with_template(client, staff_headers)
    token = _token(_invite(client, staff_headers, job_id))

    events = client.post(
        f"/api/screening/{token}/proctoring/events",
        json={"type": "tab_blur", "details": {}},
    )
    assert events.status_code == 409

    chunk = client.post(
        f"/api/screening/{token}/recordings/chunk",
        data={"kind": "camera", "seq": "0", "content_type": "video/webm"},
        files={"chunk": ("0.webm", b"x", "video/webm")},
    )
    assert chunk.status_code == 409


def test_transcribe_is_501_when_unconfigured(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    monkeypatch.setattr(
        "app.services.screening_service.get_transcriber", lambda: NullTranscriber()
    )
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    token = _token(_invite(client, staff_headers, job_id))
    _start(client, token, consent=False)

    response = client.post(
        f"/api/screening/{token}/transcribe",
        data={"content_type": "audio/webm"},
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 501, response.text
    assert response.json()["code"] == "feature_unavailable"


def test_transcribe_returns_text_when_configured(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)

    class FakeTranscriber:
        async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
            assert content_type == "audio/webm"
            assert audio == b"fake-audio"
            return "I would add a covering index."

    monkeypatch.setattr(
        "app.services.screening_service.get_transcriber", lambda: FakeTranscriber()
    )
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    token = _token(_invite(client, staff_headers, job_id))
    _start(client, token, consent=False)

    response = client.post(
        f"/api/screening/{token}/transcribe",
        data={"content_type": "audio/webm"},
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "I would add a covering index."


def test_extra_minutes_lengthens_the_round(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    invitation = _invite(client, staff_headers, job_id, extra_minutes=10)
    assert invitation["round_minutes"] == 40
    token = _token(invitation)
    _start(client, token, consent=False)

    deadline = datetime.fromisoformat(
        client.get(f"/api/screening/{token}").json()["round_deadline"]
    )
    remaining = deadline - datetime.now(UTC)
    assert timedelta(minutes=39) < remaining < timedelta(minutes=41)


def test_extend_revives_an_expired_round(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    _start(client, token, consent=False)

    _set_invitation(
        invitation["id"], {"round_deadline": datetime.now(UTC) - timedelta(minutes=1)}
    )
    assert client.get(f"/api/screening/{token}/current-question").status_code == 409

    extended = client.post(
        f"/api/invitations/{invitation['id']}/extend",
        headers=staff_headers,
        json={"minutes": 15},
    )
    assert extended.status_code == 200, extended.text
    assert extended.json()["round_deadline"] is not None
    assert client.get(f"/api/screening/{token}/current-question").status_code == 200


def test_extend_requires_recruiter_and_rejects_revoked(
    client: TestClient, staff_headers: dict, auth_headers: dict
) -> None:
    job_id = _job_with_template(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id)

    forbidden = client.post(
        f"/api/invitations/{invitation['id']}/extend",
        headers=auth_headers,
        json={"minutes": 15},
    )
    assert forbidden.status_code == 403

    assert (
        client.delete(f"/api/invitations/{invitation['id']}", headers=staff_headers).status_code
        == 204
    )
    conflict = client.post(
        f"/api/invitations/{invitation['id']}/extend",
        headers=staff_headers,
        json={"minutes": 15},
    )
    assert conflict.status_code == 409
