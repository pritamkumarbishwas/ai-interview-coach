"""Phase 8: job analytics aggregation + CSV export."""

import csv
import io

import fitz
from fastapi.testclient import TestClient

from app.schemas.invitation import ShortlistEntry
from app.services.analytics_service import AnalyticsService
from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow
from tests.test_shortlist import _invite, _token


def _entry(**overrides: object) -> ShortlistEntry:
    base: dict = {
        "invitation_id": "inv-1",
        "candidate_name": "Cand",
        "candidate_email": "cand@example.com",
        "status": "completed",
    }
    base.update(overrides)
    return ShortlistEntry(**base)


def test_aggregates_funnel_scores_and_distributions() -> None:
    entries = [
        _entry(overall_score=95.0, meets_threshold=True, integrity_level="low"),
        _entry(overall_score=85.0, meets_threshold=True, integrity_level="moderate"),
        _entry(
            overall_score=55.0,
            meets_threshold=False,
            integrity_level="high",
            decision="advance",
        ),
        _entry(status="pending", decision="pending"),
        _entry(status="expired"),
        _entry(status="revoked", decision="decline"),
    ]

    analytics = AnalyticsService().build("job-1", entries)

    assert analytics.job_id == "job-1"
    assert analytics.total_invited == 6
    assert (analytics.pending, analytics.in_progress) == (1, 0)
    assert (analytics.completed, analytics.expired, analytics.revoked) == (3, 1, 1)
    assert analytics.completion_rate == 50.0
    assert analytics.passed == 2
    assert analytics.pass_rate == 66.7
    assert analytics.average_score == 78.3
    assert analytics.median_score == 85.0
    assert {bucket.label: bucket.count for bucket in analytics.score_distribution} == {
        "0-59": 1,
        "60-69": 0,
        "70-79": 0,
        "80-89": 1,
        "90-100": 1,
    }
    assert analytics.decisions == {"pending": 4, "advance": 1, "hold": 0, "decline": 1}
    assert analytics.integrity_distribution == {
        "low": 1,
        "moderate": 1,
        "elevated": 0,
        "high": 1,
        "unknown": 0,
    }


def test_empty_pipeline_has_zeroed_rates_and_full_bands() -> None:
    analytics = AnalyticsService().build("job-empty", [])
    assert analytics.total_invited == 0
    assert analytics.completion_rate == 0.0
    assert analytics.pass_rate == 0.0
    assert analytics.average_score == 0.0
    assert analytics.median_score == 0.0
    assert [bucket.count for bucket in analytics.score_distribution] == [0, 0, 0, 0, 0]


def test_median_averages_the_middle_pair() -> None:
    entries = [_entry(overall_score=score) for score in (60.0, 70.0, 80.0, 100.0)]
    assert AnalyticsService().build("job-1", entries).median_score == 75.0


def test_csv_is_parseable_and_defangs_formulas() -> None:
    entries = [
        _entry(
            candidate_name="=SUM(A1:A9)",
            candidate_email="evil+inject@example.com",
            overall_score=88.0,
            threshold=70.0,
            meets_threshold=True,
            percentile=75.0,
            integrity_level="low",
            integrity_score=94,
        ),
        _entry(status="pending", candidate_name="-2", candidate_email="waiting@example.com"),
    ]

    text = AnalyticsService().to_csv(entries)
    rows = list(csv.reader(io.StringIO(text)))

    assert rows[0][0] == "candidate_name"
    assert "overall_score" in rows[0]
    # A leading "=" is neutralized so a spreadsheet never evaluates it.
    assert rows[1][0] == "'=SUM(A1:A9)"
    assert rows[1][1] == "evil+inject@example.com"
    assert rows[1][4] == "88.0"
    assert rows[1][6] == "yes"
    # Unscored candidates leave the advisory columns blank, not zero.
    assert rows[2][4] == "0.0"
    assert rows[2][7] == ""
    assert rows[2][9] == ""


def test_analytics_endpoint_reports_a_job(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    finished = _invite(client, staff_headers, job_id, "done@example.com")
    _invite(client, staff_headers, job_id, "waiting@example.com")
    _run_candidate_flow(client, _token(finished))

    response = client.get(
        "/api/invitations/analytics", headers=staff_headers, params={"job_id": job_id}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_invited"] == 2
    assert body["completed"] == 1
    assert body["pending"] == 1
    assert body["completion_rate"] == 50.0
    assert body["pass_rate"] == 100.0
    assert body["average_score"] == 72.0


def test_csv_export_endpoint_downloads_rows(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    finished = _invite(client, staff_headers, job_id, "done@example.com")
    _run_candidate_flow(client, _token(finished))

    response = client.get(
        "/api/invitations/export", headers=staff_headers, params={"job_id": job_id}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][0] == "candidate_name"
    assert len(rows) == 2
    assert rows[1][1] == "done@example.com"
    assert rows[1][4] == "72.0"


def test_analytics_and_export_access_control(
    client: TestClient, staff_headers: dict, auth_headers: dict
) -> None:
    job_id = _job_with_rubric(client, staff_headers)
    unknown = {"job_id": "64b000000000000000000000"}

    for path in (
        "/api/invitations/analytics",
        "/api/invitations/export",
        "/api/invitations/export.pdf",
    ):
        assert client.get(path, headers=auth_headers, params={"job_id": job_id}).status_code == 403
        assert client.get(path, headers=staff_headers, params=unknown).status_code == 404


def test_pdf_export_returns_a_pdf(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    finished = _invite(client, staff_headers, job_id, "done@example.com")
    _run_candidate_flow(client, _token(finished))

    response = client.get(
        "/api/invitations/export.pdf", headers=staff_headers, params={"job_id": job_id}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "private, no-store"
    # A real PDF starts with the %PDF- header.
    assert response.content.startswith(b"%PDF")

    with fitz.open(stream=response.content, filetype="pdf") as doc:
        text = "\n".join(page.get_text() for page in doc)
    assert "Screening summary" in text
    assert "Backend Engineer" in text
    assert "done@example.com" not in text  # names only, no PII leakage in summary
    assert "done" in text
