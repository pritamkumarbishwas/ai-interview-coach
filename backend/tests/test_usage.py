"""Phase 9: LLM cost tracking (price book, per-call recording, admin rollup)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import settings
from app.core.pricing import estimate_cost
from app.services.llm_service import LLMService
from tests.conftest import _with_mongo


class Score(BaseModel):
    score: int


class MockClient:
    """A client whose completion carries token usage."""

    def __init__(self, content: str = '{"score": 8}', prompt: int = 1000, completion: int = 500):
        self._content = content
        self._usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self._usage)


def _run(work):
    box: dict = {}

    async def runner(db) -> None:
        box["value"] = await work(db)

    _with_mongo(runner)
    return box.get("value")


def test_estimate_cost_uses_prices_and_overrides() -> None:
    # 1M input at 2.50 + 500k output at 10.00 = 2.50 + 5.00.
    assert estimate_cost("gpt-4o", 1_000_000, 500_000) == 7.5
    # Unknown model is free (and warned once) so tokens are never lost.
    assert estimate_cost("nope-model", 1_000, 1_000) == 0.0
    # An override takes precedence over the built-in table.
    assert estimate_cost("gpt-4o", 1_000_000, 0, {"gpt-4o": (1.0, 1.0)}) == 1.0


def test_records_usage_into_the_request_database(monkeypatch) -> None:
    """A completion with usage writes one metered record for the request's db."""
    _run(lambda db: db.llm_usage.delete_many({}))

    service = LLMService()
    service.client = MockClient(prompt=2000, completion=1000)
    monkeypatch.setattr(settings, "llm_cost_tracking_enabled", True)

    async def with_context(db) -> None:
        # Mimic the request middleware binding the database for this call.
        from app.core.usage import usage_db

        token = usage_db.set(db)
        try:
            await service.generate_structured("Evaluate", Score)
        finally:
            usage_db.reset(token)

    _run(with_context)

    async def read(db):
        return await db.llm_usage.find_one({})

    row = _run(read)
    assert row is not None
    assert row["prompt_tokens"] == 2000
    assert row["completion_tokens"] == 1000
    assert row["total_tokens"] == 3000
    expected = estimate_cost(service.model, 2000, 1000, settings.llm_pricing_overrides)
    assert row["cost_usd"] == expected
    assert row["model"] == service.model


def test_missing_usage_attribute_records_nothing(monkeypatch) -> None:
    _run(lambda db: db.llm_usage.delete_many({}))

    service = LLMService()
    service.client = MockClient(content='{"score": 1}')
    # A completion without a `usage` attribute is simply not metered.
    service.client._usage = None

    async def with_context(db) -> None:
        from app.core.usage import usage_db

        token = usage_db.set(db)
        try:
            await service.generate_structured("Evaluate", Score)
        finally:
            usage_db.reset(token)

    _run(with_context)
    assert _run(lambda db: db.llm_usage.count_documents({})) == 0


def test_usage_summary_endpoint_rolls_up_llm_cost(
    client: TestClient, admin_headers: dict, staff_headers: dict
) -> None:
    async def seed(db) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.llm_usage.insert_many(
            [
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 0,
                    "total_tokens": 1_000_000,
                    "cost_usd": 2.5,
                    "actor_id": None,
                    "created_at": now,
                },
                {
                    "provider": "groq",
                    "model": "openai/gpt-oss-20b",
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 0,
                    "total_tokens": 1_000_000,
                    "cost_usd": 0.1,
                    "actor_id": None,
                    "created_at": now,
                },
            ]
        )

    _run(seed)

    # Cost data is admin-only.
    assert client.get("/api/usage/summary", headers=staff_headers).status_code == 403

    response = client.get("/api/usage/summary", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["calls"] == 2
    assert body["prompt_tokens"] == 2_000_000
    assert body["cost_usd"] == 2.6
    # Models are ordered by spend, most expensive first.
    assert [row["model"] for row in body["by_model"]] == [
        "gpt-4o",
        "openai/gpt-oss-20b",
    ]
