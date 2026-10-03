import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MONGO_DB_NAME", "test_ai_interview_coach")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("JWT_EXPIRES_MINUTES", "60")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import app


def _clear_database() -> None:
    async def clear() -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.core.config import settings

        client = AsyncIOMotorClient(settings.mongo_uri)
        await client.drop_database(settings.mongo_db_name)

    asyncio.run(clear())


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _clear_database()
    yield
    _clear_database()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def registered_user(client: TestClient) -> dict:
    payload = {
        "name": "Test User",
        "email": f"test.user.{uuid4().hex[:10]}@example.com",
        "password": "supersecret123",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


@pytest.fixture()
def auth_headers(client: TestClient, registered_user: dict) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_user(client: TestClient, email: str, password: str = "password1234") -> dict:
    """Register a user directly in the database (no HTTP round trip)."""

    async def create() -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        from app.core.config import settings
        from app.models.user import User

        db_client = AsyncIOMotorClient(settings.mongo_uri)
        db = db_client[settings.mongo_db_name]

        user = User(name="Direct User", email=email, password_hash=hash_password(password))
        doc = user.model_dump(by_alias=True, exclude={"id"})
        await db.users.insert_one(doc)

    asyncio.run(create())
    return {"email": email, "password": password}
