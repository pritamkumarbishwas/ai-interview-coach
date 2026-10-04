"""CORS at the HTTP level: allowed origins, preflight, lockdown headers.

Settings-level validation (comma parsing, production wildcard rejection) lives
in `test_config.py`; these tests exercise the actual middleware.
"""

from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "http://localhost:3000"


def test_simple_request_from_allowed_origin_gets_headers(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    # `Origin` in the cache key so shared caches never mix responses.
    assert "origin" in response.headers.get("vary", "").lower()


def test_simple_request_from_disallowed_origin_has_no_cors_headers(
    client: TestClient,
) -> None:
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None


def test_preflight_from_allowed_origin_lists_needed_methods_and_headers(
    client: TestClient,
) -> None:
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    methods = response.headers["access-control-allow-methods"]
    for method in ("GET", "POST", "PATCH", "DELETE"):
        assert method in methods
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    # The SPA uses a Bearer header, never cookies: credentialed CORS is off.
    assert response.headers.get("access-control-allow-credentials") is None


def test_preflight_from_disallowed_origin_is_rejected(client: TestClient) -> None:
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code in (400, 403)
    assert response.headers.get("access-control-allow-origin") is None


def test_preflight_does_not_allow_unlisted_methods(client: TestClient) -> None:
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "PUT",
        },
    )
    # PUT is not in the allow-list, so the browser will block the request.
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        assert "PUT" not in response.headers.get("access-control-allow-methods", "")
