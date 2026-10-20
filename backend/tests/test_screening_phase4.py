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


def test_extend_pending_adds_to_the_round_budget(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="off")
    invitation = _invite(client, staff_headers, job_id)
    assert invitation["round_deadline"] is None

    extended = client.post(
        f"/api/invitations/{invitation['id']}/extend",
        headers=staff_headers,
        json={"minutes": 15},
    )
    assert extended.status_code == 200, extended.text
    body = extended.json()
    assert body["round_minutes"] == 45
    assert body["round_deadline"] is None

    token = _token(invitation)
    _start(client, token, consent=False)
    deadline = datetime.fromisoformat(
        client.get(f"/api/screening/{token}").json()["round_deadline"]
    )
    remaining = deadline - datetime.now(UTC)
    assert timedelta(minutes=44) < remaining < timedelta(minutes=46)


def test_completed_invitation_is_terminal(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(
        client, staff_headers, proctoring_mode="off", target=1
    )
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    question_id = _start(client, token, consent=False)

    answered = client.post(
        f"/api/screening/{token}/questions/{question_id}/answer",
        json={"answer": "A concise answer."},
    )
    assert answered.json()["status"] == "completed"
    assert _read_invitation(invitation["id"])["status"] == "completed"

    # The candidate can still see the terminal session, but cannot act on it.
    assert client.get(f"/api/screening/{token}").status_code == 200
    assert client.get(f"/api/screening/{token}/current-question").status_code == 409
    assert (
        client.post(f"/api/screening/{token}/start", json={"consent": False}).status_code
        == 409
    )
    # Completed sessions stay reviewable, but their link can be revoked.
    assert (
        client.delete(
            f"/api/invitations/{invitation['id']}", headers=staff_headers
        ).status_code
        == 204
    )
    assert client.get(f"/api/screening/{token}").status_code == 409
    listed = client.get(
        "/api/invitations", headers=staff_headers, params={"job_id": job_id}
    ).json()
    row = next(item for item in listed if item["id"] == invitation["id"])
    assert row["status"] == "completed"
    assert row["link_revoked_at"] is not None


def test_completed_recording_cannot_be_restarted_or_overwritten(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(
        client, staff_headers, proctoring_mode="strict", target=1
    )
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    question_id = _start(client, token)

    endpoint = f"/api/screening/{token}/recordings/chunk"
    first = client.post(
        endpoint,
        data={"kind": "camera", "seq": "0", "finalize": "false", "content_type": "video/webm"},
        files={"chunk": ("0.webm", b"original", "video/webm")},
    )
    assert first.status_code == 204, first.text

    answered = client.post(
        f"/api/screening/{token}/questions/{question_id}/answer",
        json={"answer": "A concise answer."},
    )
    assert answered.json()["status"] == "completed"

    # Restarting would delete the GridFS recording: not allowed after completion.
    restart = client.post(
        endpoint,
        data={"kind": "camera", "seq": "0", "finalize": "false", "content_type": "video/webm"},
        files={"chunk": ("0.webm", b"replacement", "video/webm")},
    )
    assert restart.status_code == 409, restart.text

    # The in-flight tail and the finalize marker may still land.
    tail = client.post(
        endpoint,
        data={"kind": "camera", "seq": "1", "finalize": "false", "content_type": "video/webm"},
        files={"chunk": ("1.webm", b"-tail", "video/webm")},
    )
    assert tail.status_code == 204, tail.text
    sealed = client.post(
        endpoint,
        data={"kind": "camera", "seq": "2", "finalize": "true", "content_type": "video/webm"},
        files={"chunk": ("2.webm", b"", "video/webm")},
    )
    assert sealed.status_code == 204, sealed.text

    # Once sealed, neither bytes nor proctoring events can be appended.
    after = client.post(
        endpoint,
        data={"kind": "camera", "seq": "3", "finalize": "false", "content_type": "video/webm"},
        files={"chunk": ("3.webm", b"x", "video/webm")},
    )
    assert after.status_code == 409, after.text
    event = client.post(
        f"/api/screening/{token}/proctoring/events",
        json={"type": "tab_blur", "details": {}},
    )
    assert event.status_code == 409, event.text

    download = client.get(
        f"/api/invitations/{invitation['id']}/recordings/camera", headers=staff_headers
    )
    assert download.status_code == 200, download.text
    assert download.content == b"original-tail"


def test_completed_link_eventually_expires(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(
        client, staff_headers, proctoring_mode="off", target=1
    )
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    question_id = _start(client, token, consent=False)
    client.post(
        f"/api/screening/{token}/questions/{question_id}/answer",
        json={"answer": "A concise answer."},
    )

    _set_invitation(
        invitation["id"],
        {
            "expires_at": datetime.now(UTC) - timedelta(days=8),
            "completed_at": datetime.now(UTC) - timedelta(days=7),
        },
    )
    assert client.get(f"/api/screening/{token}").status_code == 409


def test_extend_reopens_an_expired_pending_link(
    client: TestClient, staff_headers: dict
) -> None:
    job_id = _job_with_template(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    _set_invitation(
        invitation["id"],
        {"status": "expired", "expires_at": datetime.now(UTC) - timedelta(days=1)},
    )
    assert client.get(f"/api/screening/{token}").status_code == 409

    extended = client.post(
        f"/api/invitations/{invitation['id']}/extend",
        headers=staff_headers,
        json={"minutes": 15},
    )
    assert extended.status_code == 200, extended.text
    body = extended.json()
    assert body["status"] == "pending"
    assert datetime.fromisoformat(body["expires_at"]) > datetime.now(UTC)

    reopened = client.get(f"/api/screening/{token}")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "pending"


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
