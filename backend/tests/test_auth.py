from fastapi.testclient import TestClient

from tests.conftest import make_user


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
    user = make_user(client, email)
    login = client.post("/api/auth/login", json=user)
    token = login.json()["access_token"]

    async def delete_user() -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.core.config import settings

        db_client = AsyncIOMotorClient(settings.mongo_uri)
        db = db_client[settings.mongo_db_name]

        await db.users.delete_one({"email": email})

    import asyncio

    asyncio.run(delete_user())

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
