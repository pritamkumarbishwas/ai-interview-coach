from datetime import UTC, datetime

import fitz
import pytest
from fastapi.testclient import TestClient

from tests.conftest import insert_job_description

RESUME_SERVICE_LLM = "app.services.resume_service.llm_service.generate_structured"
JD_SERVICE_LLM = "app.services.job_description_service.llm_service.generate_structured"


def make_pdf(text: str = "Jane Doe - Python engineer with 5 years of experience.") -> bytes:
    """Build a small but valid PDF, so the upload happy path is testable."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


async def fake_resume_extraction(prompt: str, schema, **kwargs):
    return schema(
        skills=["Python", "FastAPI"],
        experience=[],
        projects=[],
        education=[],
    )


def test_list_resumes_requires_auth(client: TestClient) -> None:
    response = client.get("/api/resumes")
    assert response.status_code == 401


def test_upload_rejects_unsupported_extension(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF and DOCX" in response.json()["detail"]


def test_upload_rejects_content_that_does_not_match_extension(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", b"not a real pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert "extension" in response.json()["detail"]


def test_upload_rejects_corrupt_pdf(client: TestClient, auth_headers: dict) -> None:
    payload = b"%PDF-1.7\n%garbage that pymupdf cannot open"
    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 400
    assert "parse" in response.json()["detail"].lower()


def test_upload_rejects_empty_file(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_oversized_body_is_rejected(client: TestClient, auth_headers: dict) -> None:
    response = client.get(
        "/api/resumes",
        headers={**auth_headers, "Content-Length": str(50 * 1024 * 1024)},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_upload_valid_pdf_is_listed_fetched_and_deleted(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RESUME_SERVICE_LLM, fake_resume_extraction)

    created = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", make_pdf(), "application/pdf")},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["filename"] == "resume.pdf"
    assert body["structured_data"]["skills"] == ["Python", "FastAPI"]
    resume_id = body["id"]

    listed = client.get("/api/resumes", headers=auth_headers)
    assert listed.status_code == 200
    summaries = listed.json()
    assert any(item["id"] == resume_id for item in summaries)
    assert all("raw_text" not in item for item in summaries)

    detail = client.get(f"/api/resumes/{resume_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["raw_text"]
    # The stored file name is an implementation detail and never leaves the API.
    assert "storage_key" not in detail.json()

    assert client.delete(f"/api/resumes/{resume_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/resumes/{resume_id}", headers=auth_headers).status_code == 404


def test_upload_returns_service_unavailable_when_llm_is_down(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(prompt: str, schema, **kwargs):
        raise RuntimeError("llm is down")

    monkeypatch.setattr(RESUME_SERVICE_LLM, boom)

    response = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", make_pdf(), "application/pdf")},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"


def test_get_resume_with_invalid_id_is_404(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/resumes/not-an-object-id", headers=auth_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Resume not found", "code": "not_found"}


def test_delete_resume_with_invalid_id_is_404(client: TestClient, auth_headers: dict) -> None:
    response = client.delete("/api/resumes/not-an-object-id", headers=auth_headers)
    assert response.status_code == 404


def test_delete_resume_of_another_user_is_404(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RESUME_SERVICE_LLM, fake_resume_extraction)
    created = client.post(
        "/api/resumes/upload",
        headers=auth_headers,
        files={"file": ("resume.pdf", make_pdf(), "application/pdf")},
    )
    resume_id = created.json()["id"]

    # A second account must not be able to read or delete someone else's resume.
    other_email = "other.user@example.com"
    register = client.post(
        "/api/auth/register",
        json={"name": "Other User", "email": other_email, "password": "strongpassword1"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": other_email, "password": "strongpassword1"},
    )
    assert register.status_code == 201
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get(f"/api/resumes/{resume_id}", headers=other).status_code == 404
    assert client.delete(f"/api/resumes/{resume_id}", headers=other).status_code == 404
    # The owner's copy is untouched.
    assert client.get(f"/api/resumes/{resume_id}", headers=auth_headers).status_code == 200


def test_list_resumes_returns_summaries(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/resumes", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_job_description_requires_company(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/job-descriptions",
        headers=auth_headers,
        json={"title": "Backend Engineer", "raw_text": "x" * 60},
    )
    assert response.status_code == 422


def test_job_description_requires_auth(client: TestClient) -> None:
    assert client.get("/api/job-descriptions").status_code == 401
    assert client.post("/api/job-descriptions", json={}).status_code == 401


def test_job_description_with_invalid_id_is_404(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/job-descriptions/nope", headers=auth_headers)
    assert response.status_code == 404


def test_job_description_create_list_get_delete(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_extract(prompt: str, schema, **kwargs):
        return schema(
            role_title="Backend Engineer",
            required_skills=["FastAPI"],
            responsibilities=["Build APIs"],
        )

    monkeypatch.setattr(JD_SERVICE_LLM, fake_extract)

    payload = {
        "title": "Backend Engineer",
        "company": "Acme",
        "raw_text": "Own our FastAPI services and MongoDB collections end to end.",
    }
    created = client.post("/api/job-descriptions", headers=auth_headers, json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "Backend Engineer"
    assert body["structured_data"]["required_skills"] == ["FastAPI"]
    jd_id = body["id"]

    listed = client.get("/api/job-descriptions", headers=auth_headers)
    assert listed.status_code == 200
    summaries = listed.json()
    assert any(item["id"] == jd_id for item in summaries)
    assert all("raw_text" not in item for item in summaries)
    assert all("snippet" in item for item in summaries)

    detail = client.get(f"/api/job-descriptions/{jd_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["raw_text"] == payload["raw_text"]

    assert client.delete(f"/api/job-descriptions/{jd_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/job-descriptions/{jd_id}", headers=auth_headers).status_code == 404


def test_job_description_saved_when_llm_unavailable(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(prompt: str, schema, **kwargs):
        raise RuntimeError("llm is down")

    monkeypatch.setattr(JD_SERVICE_LLM, boom)

    response = client.post(
        "/api/job-descriptions",
        headers=auth_headers,
        json={"title": "SRE", "company": "Acme", "raw_text": "Keep the cluster healthy."},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["structured_data"]["role_title"] == "SRE"
    assert body["structured_data"]["required_skills"] == []


def test_job_description_list_handles_legacy_documents(
    client: TestClient, auth_headers: dict
) -> None:
    """Older documents have no `snippet` and may store null lists."""
    me = client.get("/api/auth/me", headers=auth_headers).json()
    insert_job_description(
        {
            "user_id": me["id"],
            "title": "Legacy Role",
            "company": "Old Co",
            "raw_text": "A posting saved before the snippet field existed.",
            "structured_data": {"responsibilities": None},
            "created_at": datetime.now(UTC),
        }
    )

    response = client.get("/api/job-descriptions", headers=auth_headers)
    assert response.status_code == 200
    legacy = next(item for item in response.json() if item["title"] == "Legacy Role")
    assert legacy["snippet"] == ""
