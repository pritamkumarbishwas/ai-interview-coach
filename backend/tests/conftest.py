# ruff: noqa: I001
# tests/_bootstrap.py must be imported before any `app.*` module (it sets the
# test environment and starts the ephemeral MongoDB), so it intentionally
# precedes the stdlib / third-party import blocks below.
from tests import _bootstrap

import asyncio
import math
import re
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import fitz
import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models.user import User

RESUME_SERVICE_LLM = "app.services.resume_service.llm_service.generate_structured"
# The interview flow shares one `llm_service` singleton with resume/JD
# extraction, so one patched method must dispatch every schema in the flow.
INTERVIEW_LLM = "app.services.interview_service.llm_service.generate_structured"


def make_pdf(text: str = "Jane Doe - Python engineer with 5 years of experience.") -> bytes:
    """Build a small but valid PDF, so the upload happy path is testable."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


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
    if _bootstrap.MONGO_SERVER is not None:
        # Stop the ephemeral mongod we started in tests/_bootstrap.py.
        _bootstrap.MONGO_SERVER.close()


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the real embedding model with a deterministic bag-of-words fake.

    fastembed downloads a ~90MB ONNX model on first use — tests must never
    trigger that. Tokens are hashed into fixed buckets with crc32 (stable
    across processes, unlike hash()), then L2-normalized so cosine ranking
    still reflects token overlap.
    """

    def embed_texts(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            buckets = [0.0] * 32
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                buckets[zlib.crc32(token.encode()) % 32] += 1.0
            norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
            vectors.append([value / norm for value in buckets])
        return vectors

    monkeypatch.setattr("app.services.embedding_service.embedding_service.embed_texts", embed_texts)


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


@pytest.fixture()
def staff_headers(client: TestClient) -> dict[str, str]:
    """Auth headers for a recruiter (can manage jobs and templates)."""
    return login(client, make_user(f"staff.{uuid4().hex[:10]}@example.com", role="recruiter"))


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    """Auth headers for an admin (can manage staff and read the audit log)."""
    return login(client, make_user(f"admin.{uuid4().hex[:10]}@example.com", role="admin"))


@dataclass
class Env:
    """A schema-dispatching fake LLM shared by interview-flow tests."""

    setup: object  # callable(target: int) -> dict
    prompts: list[str] = field(default_factory=list)
    dispatcher: object = None


@pytest.fixture()
def env(client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch) -> Env:
    """Shared LLM dispatcher plus a helper that creates a started interview."""
    prompts: list[str] = []
    question_calls = 0

    async def dispatcher(prompt: str, schema, **kwargs):
        nonlocal question_calls
        prompts.append(prompt)
        name = schema.__name__
        if name == "ResumeStructuredData":
            return schema(skills=["Python", "FastAPI"], experience=[], projects=[], education=[])
        if name == "JobDescriptionStructuredData":
            return schema(
                role_title="Backend Engineer",
                required_skills=["FastAPI"],
                responsibilities=["Build APIs"],
            )
        if name == "QuestionGeneration":
            question_calls += 1
            return schema(
                question=f"Question number {question_calls}?",
                topic=f"topic-{question_calls}",
            )
        if name == "EvaluationGeneration":
            return schema(
                scores={
                    "technical": 80,
                    "relevance": 85,
                    "completeness": 70,
                    "structure": 75,
                    "clarity": 90,
                },
                strengths=["clear reasoning"],
                weaknesses=["missed edge cases"],
                feedback="Solid answer; cover failure modes next time.",
                improved_answer="A model answer.",
                next_step="new_topic",
            )
        if name == "ReportGeneration":
            return schema(
                narrative="Solid fundamentals; tighten structure and cover edge cases.",
                preparation_plan=[
                    {
                        "focus": "Failure modes",
                        "actions": ["Study timeouts and retries", "Practice EXPLAIN"],
                    },
                ],
            )
        raise AssertionError(f"unexpected schema {name}")

    monkeypatch.setattr(RESUME_SERVICE_LLM, dispatcher)

    def setup(target: int = 3) -> dict:
        resume = client.post(
            "/api/resumes/upload",
            headers=auth_headers,
            files={"file": ("resume.pdf", make_pdf(), "application/pdf")},
        )
        assert resume.status_code == 201, resume.text
        jd = client.post(
            "/api/job-descriptions",
            headers=auth_headers,
            json={
                "title": "Backend Engineer",
                "company": "Acme",
                "raw_text": "Own our FastAPI services and MongoDB collections.",
            },
        )
        assert jd.status_code == 201, jd.text
        created = client.post(
            "/api/interviews",
            headers=auth_headers,
            json={
                "resume_id": resume.json()["id"],
                "jd_id": jd.json()["id"],
                "role": "Backend Engineer",
                "level": "mid",
                "type": "technical",
                "difficulty": "intermediate",
                # Flow tests exercise questions/answers/report, not proctoring;
                # "off" skips the consent-before-start requirement.
                "proctoring_mode": "off",
                "target_questions": target,
            },
        )
        assert created.status_code == 201, created.text
        started = client.post(f"/api/interviews/{created.json()['id']}/start", headers=auth_headers)
        assert started.status_code == 200, started.text
        return {
            "id": created.json()["id"],
            "question_id": started.json()["question"]["id"],
            "target": target,
        }

    return Env(setup=setup, prompts=prompts, dispatcher=dispatcher)


def make_user(
    email: str,
    password: str = "password1234",
    role: str = "candidate",
) -> dict:
    """Insert a user directly in the database (no HTTP round trip)."""

    async def create(db) -> None:
        user = User(
            name="Direct User",
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        await db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))

    _with_mongo(create)
    return {"email": email, "password": password}


def login(client: TestClient, creds: dict) -> dict[str, str]:
    """Log in a pre-created user and return ready-to-use auth headers."""
    response = client.post("/api/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def delete_user(email: str) -> None:
    async def delete(db) -> None:
        await db.users.delete_one({"email": email})

    _with_mongo(delete)


def insert_job_description(doc: dict) -> None:
    """Insert a raw job-description document (used for legacy-shape tests)."""

    async def insert(db) -> None:
        await db.job_descriptions.insert_one(doc)

    _with_mongo(insert)
