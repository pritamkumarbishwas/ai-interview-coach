from fastapi.testclient import TestClient


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


def test_get_resume_with_invalid_id_is_404(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/resumes/not-an-object-id", headers=auth_headers)
    assert response.status_code == 404


def test_delete_resume_with_invalid_id_is_404(client: TestClient, auth_headers: dict) -> None:
    response = client.delete("/api/resumes/not-an-object-id", headers=auth_headers)
    assert response.status_code == 404


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


def test_job_description_with_invalid_id_is_404(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/job-descriptions/nope", headers=auth_headers)
    assert response.status_code == 404
