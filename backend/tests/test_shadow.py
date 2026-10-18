"""Phase 10: shadow mode — agreement between the advisory AI and human decisions."""

from fastapi.testclient import TestClient

from app.schemas.invitation import ShortlistEntry
from app.services.shadow_service import MAX_DISAGREEMENTS, ShadowService
from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow
from tests.test_shortlist import _invite, _token


def _entry(**overrides: object) -> ShortlistEntry:
    base: dict = {
        "invitation_id": "inv-1",
        "candidate_name": "Cand",
        "candidate_email": "cand@example.com",
        "status": "completed",
        "threshold": 70.0,
        "decision": "advance",
    }
    base.update(overrides)
    return ShortlistEntry(**base)


def test_counts_agreements_and_both_disagreement_directions() -> None:
    entries = [
        _entry(meets_threshold=True, decision="advance"),  # agreed advance
        _entry(meets_threshold=False, decision="decline"),  # agreed review
        _entry(meets_threshold=True, decision="hold"),  # AI lenient
        _entry(meets_threshold=False, decision="advance"),  # AI strict
    ]

    report = ShadowService().build("job-1", entries)

    assert report.job_id == "job-1"
    assert report.advisory is True
    assert report.compared == 4
    assert report.agreed == 2
    assert report.agreement_rate == 50.0
    assert (report.agreed_advance, report.agreed_review) == (1, 1)
    assert (report.ai_lenient, report.ai_strict) == (1, 1)
    assert report.advanced_rate_ai == 50.0
    assert report.advanced_rate_human == 50.0
    assert report.leniency_gap == 0.0
    assert report.bias == "aligned"
    assert report.sufficient_sample is False
    directions = {item.direction for item in report.disagreements}
    assert directions == {"ai_lenient", "ai_strict"}


def test_uncomparable_rows_are_reported_as_exclusions() -> None:
    entries = [
        _entry(status="pending", decision="pending"),  # never finished
        _entry(threshold=0.0),  # completed but no threshold -> no AI signal
        _entry(decision="pending"),  # comparable signal, but nobody decided yet
    ]

    report = ShadowService().build("job-1", entries)

    assert report.compared == 0
    assert report.agreement_rate == 0.0
    assert report.disagreements == []
    assert report.excluded_not_completed == 1
    assert report.excluded_no_threshold == 1
    assert report.excluded_awaiting_decision == 1


def test_a_thresholdless_round_is_never_counted_as_agreement() -> None:
    """Without a threshold the scorecard makes no call, so nothing is comparable."""
    entries = [_entry(threshold=0.0, meets_threshold=False, decision="decline")]

    report = ShadowService().build("job-1", entries)

    assert report.compared == 0
    assert report.excluded_no_threshold == 1


def test_lenient_bias_when_the_ai_advances_more_than_the_panel() -> None:
    entries = [_entry(meets_threshold=True, decision="decline") for _ in range(10)]

    report = ShadowService().build("job-1", entries)

    assert report.compared == 10
    assert report.ai_lenient == 10
    assert report.advanced_rate_ai == 100.0
    assert report.advanced_rate_human == 0.0
    assert report.leniency_gap == 100.0
    assert report.bias == "lenient"
    assert report.sufficient_sample is True


def test_strict_bias_when_the_panel_advances_more_than_the_ai() -> None:
    entries = [_entry(meets_threshold=False, decision="advance") for _ in range(10)]

    report = ShadowService().build("job-1", entries)

    assert report.ai_strict == 10
    assert report.leniency_gap == -100.0
    assert report.bias == "strict"


def test_disagreements_are_capped_and_worst_first() -> None:
    entries = [
        _entry(
            invitation_id=f"inv-{index}",
            meets_threshold=True,
            decision="decline",
            overall_score=71.0 + index,
            threshold=70.0,
            candidate_name=f"Cand {index:02d}",
        )
        for index in range(MAX_DISAGREEMENTS + 5)
    ]

    report = ShadowService().build("job-1", entries)

    assert report.ai_lenient == MAX_DISAGREEMENTS + 5
    assert len(report.disagreements) == MAX_DISAGREEMENTS
    # The candidate furthest above the threshold is the most notable disagreement.
    assert report.disagreements[0].candidate_name == f"Cand {MAX_DISAGREEMENTS + 4:02d}"


def test_shadow_endpoint_reports_agreement(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    advanced = _invite(client, staff_headers, job_id, "yes@example.com")
    held = _invite(client, staff_headers, job_id, "no@example.com")
    _run_candidate_flow(client, _token(advanced))
    _run_candidate_flow(client, _token(held))

    # The stub scores every candidate at 72 vs a threshold of 70: the AI says
    # "advance" for both, so the panel is the only source of disagreement.
    client.patch(
        f"/api/invitations/{advanced['id']}/decision",
        headers=staff_headers,
        json={"decision": "advance"},
    )
    client.patch(
        f"/api/invitations/{held['id']}/decision",
        headers=staff_headers,
        json={"decision": "decline"},
    )

    response = client.get(
        "/api/invitations/shadow", headers=staff_headers, params={"job_id": job_id}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["compared"] == 2
    assert body["agreed"] == 1
    assert body["agreement_rate"] == 50.0
    assert body["ai_lenient"] == 1
    assert body["bias"] == "lenient"
    assert [item["direction"] for item in body["disagreements"]] == ["ai_lenient"]
    assert body["disagreements"][0]["candidate_name"] == "no"


def test_shadow_access_control(
    client: TestClient, staff_headers: dict, auth_headers: dict
) -> None:
    job_id = _job_with_rubric(client, staff_headers)
    unknown = {"job_id": "64b000000000000000000000"}

    assert (
        client.get("/api/invitations/shadow", headers=auth_headers, params={"job_id": job_id})
        .status_code
        == 403
    )
    assert (
        client.get("/api/invitations/shadow", headers=staff_headers, params=unknown).status_code
        == 404
    )
