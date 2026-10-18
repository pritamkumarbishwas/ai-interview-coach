"""Phase 5: advisory integrity report aggregation (passive signals, no verdict)."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.models.interview import (
    Interview,
    ProctoringEvent,
    ProctoringSession,
)
from app.services.integrity_service import IntegrityService
from tests.test_screening import _invite, _job_with_template, _patch_llm, _token


def _start(client: TestClient, token: str, consent: bool = True) -> None:
    response = client.post(f"/api/screening/{token}/start", json={"consent": consent})
    assert response.status_code == 200, response.text


def test_report_scores_and_timeline(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="strict")
    invitation = _invite(client, staff_headers, job_id)
    token = _token(invitation)
    _start(client, token)

    for event_type in ("tab_blur", "camera_off", "camera_on", "paste", "window_blur"):
        response = client.post(
            f"/api/screening/{token}/proctoring/events",
            json={"type": event_type, "details": {}},
        )
        assert response.status_code == 204, response.text

    report = client.get(
        f"/api/invitations/{invitation['id']}/integrity", headers=staff_headers
    )
    assert report.status_code == 200, report.text
    body = report.json()

    assert body["advisory"] is True
    # 6 (tab_blur) + 8 (camera_off) + 4 (paste) + 3 (window_blur) = 21 -> 79.
    assert body["score"] == 79
    assert body["level"] == "moderate"
    assert body["session_started_at"] is not None

    counts = {signal["type"]: signal["count"] for signal in body["signals"]}
    assert counts == {"camera_off": 1, "tab_blur": 1, "paste": 1, "window_blur": 1}
    # The benign "camera_on" recovery is neutral and must not appear.
    assert "camera_on" not in counts
    assert len(body["moments"]) == 4


def test_report_is_advisory_when_clean(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers, proctoring_mode="strict")
    invitation = _invite(client, staff_headers, job_id)
    _start(client, _token(invitation))

    body = client.get(
        f"/api/invitations/{invitation['id']}/integrity", headers=staff_headers
    ).json()
    assert body["score"] == 100
    assert body["level"] == "low"
    assert body["signals"] == []
    assert any("No integrity signals" in note for note in body["notes"])


def test_integrity_access_control(
    client: TestClient, staff_headers: dict, auth_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch)
    job_id = _job_with_template(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id)

    # Not started yet -> conflict.
    assert (
        client.get(
            f"/api/invitations/{invitation['id']}/integrity", headers=staff_headers
        ).status_code
        == 409
    )
    # Candidates cannot read integrity.
    assert (
        client.get(
            f"/api/invitations/{invitation['id']}/integrity", headers=auth_headers
        ).status_code
        == 403
    )
    # Unknown invitation -> 404.
    assert (
        client.get("/api/invitations/64b000000000000000000000/integrity", headers=staff_headers)
        .status_code
        == 404
    )


def test_service_ignores_unlisted_events() -> None:
    interview = Interview(
        id="i1",
        user_id="u1",
        resume_id="",
        jd_id="j1",
        role="Engineer",
        proctoring_mode="strict",
        proctoring_session=ProctoringSession(
            started_at=datetime.now(UTC),
            events=[
                ProctoringEvent(type="tab_focus"),
                ProctoringEvent(type="camera_on"),
                ProctoringEvent(type="paste", details={"chars": 12}),
            ],
        ),
    )
    report = IntegrityService().build(interview)
    assert report.score == 96  # only "paste" counts
    assert [signal.type for signal in report.signals] == ["paste"]
    assert [moment.type for moment in report.moments] == ["paste"]
