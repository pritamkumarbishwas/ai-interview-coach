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
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models.user import User


def _with_mongo(work):
    """Run `work(database)` against the suite's database on a fresh event loop."""

    async def runner() -> None:
        client = AsyncIOMotorClient(settings.mongo_uri)
        try:
            await work(client[settings.mongo_db_name])
        finally:
            client.close()

    asyncio.run(runner())


def _drop_test_database() -> None:
    """Drop the suite's database before and after a run.

    `MONGO_URI` comes from `backend/.env` and may point at a shared or even a
    production cluster, so refuse to touch a database that does not look like
    a test database.
    """
    if not settings.mongo_db_name.startswith("test"):
        raise RuntimeError(
            f"Refusing to drop database {settings.mongo_db_name!r}; "
            "the test run needs a MONGO_DB_NAME that starts with 'test'."
        )
    _with_mongo(lambda db: db.client.drop_database(settings.mongo_db_name))


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _drop_test_database()
    yield
    _drop_test_database()


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


def make_user(email: str, password: str = "password1234") -> dict:
    """Insert a user directly in the database (no HTTP round trip)."""

    async def create(db) -> None:
        user = User(name="Direct User", email=email, password_hash=hash_password(password))
        await db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))

    _with_mongo(create)
    return {"email": email, "password": password}


def delete_user(email: str) -> None:
    async def delete(db) -> None:
        await db.users.delete_one({"email": email})

    _with_mongo(delete)


def insert_job_description(doc: dict) -> None:
    """Insert a raw job-description document (used for legacy-shape tests)."""

    async def insert(db) -> None:
        await db.job_descriptions.insert_one(doc)

    _with_mongo(insert)
