import pytest
from fastapi.testclient import TestClient

from tests.conftest import delete_user, make_user


def test_health_check(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_returns_user_without_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "strongpassword1",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str) and len(body["id"]) > 0
    assert body["name"] == "Alice"
    assert body["email"] == "alice@example.com"
    assert "password" not in body
    assert "password_hash" not in body
    assert "created_at" in body


def test_register_duplicate_email_conflicts(client: TestClient) -> None:
    payload = {
        "name": "Bob",
        "email": "bob@example.com",
        "password": "strongpassword1",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


def test_register_normalizes_email_case(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Carol",
            "email": "Carol.Case@Example.com",
            "password": "strongpassword1",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "carol.case@example.com"


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"name": "Dan", "email": "not-an-email", "password": "strongpassword1"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"name": "Eve", "email": "eve@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_success_returns_token(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 0
    assert body["expires_in"] > 0
    assert body["user"]["email"] == registered_user["email"]


def test_login_wrong_password_fails(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": registered_user["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_fails(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )
    assert response.status_code == 401


def test_me_returns_current_user(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


def test_me_without_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_token_of_deleted_user(client: TestClient) -> None:
    email = "deleted.user@example.com"
    user = make_user(email)
    login = client.post("/api/auth/login", json=user)
    token = login.json()["access_token"]

    delete_user(email)

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_update_profile_changes_name(
    client: TestClient, auth_headers: dict, registered_user: dict
) -> None:
    response = client.patch("/api/auth/me", headers=auth_headers, json={"name": "Renamed User"})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed User"
    assert response.json()["email"] == registered_user["email"]

    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.json()["name"] == "Renamed User"


def test_update_profile_requires_auth(client: TestClient) -> None:
    response = client.patch("/api/auth/me", json={"name": "Anyone"})
    assert response.status_code == 401


def test_update_profile_rejects_blank_name(client: TestClient, auth_headers: dict) -> None:
    response = client.patch("/api/auth/me", headers=auth_headers, json={"name": "   "})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_unauthorized_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated", "code": "unauthenticated"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "not_found"}


def test_login_is_rate_limited(
    client: TestClient, registered_user: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Throttling is off for the suite; switch it on for this test only."""
    from app.core import rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module.settings, "environment", "development")
    monkeypatch.setattr(rate_limit_module._limiter, "max_hits", 3)
    try:
        payload = {"email": registered_user["email"], "password": "wrong-password"}
        responses = [client.post("/api/auth/login", json=payload) for _ in range(4)]
    finally:
        rate_limit_module._limiter._hits.clear()

    assert [response.status_code for response in responses[:3]] == [401, 401, 401]
    throttled = responses[3]
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "rate_limited"
    assert int(throttled.headers["Retry-After"]) >= 1
