from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.services import llm_service as llm_module
from app.services.llm_service import LLMService


class MockResponseSchema(BaseModel):
    score: int = Field(ge=1, le=10)
    feedback: str


class MockAsyncOpenAI:
    """Mimics the `client.chat.completions.create(...)` surface."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.call_count = 0
        self.last_kwargs: dict = {}
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    async def _create(self, **kwargs):
        self.last_kwargs = kwargs
        index = min(self.call_count, len(self.responses) - 1)
        content = self.responses[index]
        self.call_count += 1
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "RETRY_BACKOFF_SECONDS", 0)


@pytest.mark.asyncio
async def test_generate_structured_success() -> None:
    service = LLMService()
    mock_client = MockAsyncOpenAI(['{"score": 8, "feedback": "Good job!"}'])
    service.client = mock_client

    result = await service.generate_structured("Evaluate this", MockResponseSchema)

    assert isinstance(result, MockResponseSchema)
    assert result.score == 8
    assert result.feedback == "Good job!"
    assert mock_client.call_count == 1
    assert mock_client.last_kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_generate_structured_retry_logic() -> None:
    service = LLMService()
    mock_client = MockAsyncOpenAI(
        [
            '{"score": "eight", "feedback": "Good job!"}',  # invalid type
            '{"score": 8, "feedback": "Good job!"}',  # valid
        ]
    )
    service.client = mock_client

    result = await service.generate_structured("Evaluate this", MockResponseSchema)

    assert result.score == 8
    assert mock_client.call_count == 2


@pytest.mark.asyncio
async def test_generate_structured_max_retries_exceeded() -> None:
    service = LLMService()
    mock_client = MockAsyncOpenAI(['{"score": "eight"}'])
    service.client = mock_client

    with pytest.raises(ValidationError):
        await service.generate_structured("Evaluate this", MockResponseSchema, max_retries=3)

    assert mock_client.call_count == 3
