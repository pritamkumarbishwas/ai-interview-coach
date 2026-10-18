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


class FailingAsyncOpenAI:
    """Mimics a client whose calls always raise `error`."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.call_count = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.call_count += 1
        raise self.error


class FakeStatusError(Exception):
    """Minimal stand-in for an API error that carries an HTTP status."""

    def __init__(self, status_code: int, body: dict | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.body = body


@pytest.mark.asyncio
async def test_generate_structured_does_not_retry_client_errors() -> None:
    """A 401 will fail identically on every attempt, so fail immediately."""
    service = LLMService()
    mock_client = FailingAsyncOpenAI(FakeStatusError(401))
    service.client = mock_client

    with pytest.raises(FakeStatusError):
        await service.generate_structured("Evaluate this", MockResponseSchema)

    assert mock_client.call_count == 1


@pytest.mark.asyncio
async def test_generate_structured_retries_server_errors() -> None:
    service = LLMService()
    mock_client = FailingAsyncOpenAI(FakeStatusError(503))
    service.client = mock_client

    with pytest.raises(FakeStatusError):
        await service.generate_structured("Evaluate this", MockResponseSchema)

    assert mock_client.call_count == 3


@pytest.mark.asyncio
async def test_generate_structured_retries_provider_json_rejection() -> None:
    """Groq's 400 `json_validate_failed` is a bad generation, not a bad request."""
    service = LLMService()
    error = FakeStatusError(
        400,
        body={"error": {"code": "json_validate_failed", "failed_generation": ""}},
    )
    mock_client = FailingAsyncOpenAI(error)
    service.client = mock_client

    with pytest.raises(FakeStatusError):
        await service.generate_structured("Evaluate this", MockResponseSchema)

    assert mock_client.call_count == 3


@pytest.mark.asyncio
async def test_correction_hint_names_missing_keys_without_dumping_the_error() -> None:
    """The retry instruction is concise and JSON-oriented (safe for JSON mode)."""
    from app.services.llm_service import _correction_hint

    class NeedsEducation(BaseModel):
        skills: list[str] = Field(default_factory=list)
        education: list[str]

    try:
        NeedsEducation.model_validate({"skills": ["python"]})
    except ValidationError as exc:
        hint = _correction_hint(exc)
    else:  # pragma: no cover - the model above must fail
        raise AssertionError("expected a ValidationError")

    assert "education" in hint
    assert "empty list" in hint
    # The raw pydantic dump (which JSON-mode providers can echo) is not included.
    assert "type=missing" not in hint
    assert "for further information" not in hint.lower()
