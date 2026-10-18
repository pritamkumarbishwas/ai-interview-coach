"""Phase 9: the compliance / data-processing record."""

from fastapi.testclient import TestClient

from app.core.config import settings


def test_compliance_record_is_admin_only_and_reports_controls(
    client: TestClient, admin_headers: dict, staff_headers: dict, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "deployment_region", "eu-central-1")
    monkeypatch.setattr(settings, "dpa_contact_email", "dpo@example.com")

    assert client.get("/api/compliance", headers=staff_headers).status_code == 403
    assert client.get("/api/compliance").status_code == 401

    response = client.get("/api/compliance", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["deployment_region"] == "eu-central-1"
    assert body["dpa_contact_email"] == "dpo@example.com"
    assert body["data_retention_days"] == settings.data_retention_days
    assert isinstance(body["encryption_at_rest"], bool)
    assert any("right to erasure" in row for row in body["data_subject_endpoints"])
    assert body["subprocessors"] and "LLM provider" in body["subprocessors"][0]["name"]
