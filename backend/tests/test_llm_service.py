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


class RecordingClient:
    """Raises `errors[i]` (when set), else returns `contents[i]`, per call."""

    def __init__(
        self,
        contents: list[str],
        errors: list[Exception | None] | None = None,
    ) -> None:
        self.contents = contents
        self.errors = errors or [None] * len(contents)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        index = len(self.calls)
        self.calls.append(kwargs)
        error = self.errors[index] if index < len(self.errors) else None
        if error is not None:
            raise error
        content = self.contents[min(index, len(self.contents) - 1)]
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_retry_keeps_json_mode_and_adds_correction_hint() -> None:
    """After a `json_validate_failed` 400, retry keeps JSON mode with a hint."""
    service = LLMService()
    error = FakeStatusError(
        400,
        body={"error": {"code": "json_validate_failed", "failed_generation": ""}},
    )
    client = RecordingClient(
        ['{"score": 7, "feedback": "ok"}'],
        errors=[error],
    )
    service.client = client

    result = await service.generate_structured("Evaluate this", MockResponseSchema)

    assert result.score == 7
    assert len(client.calls) == 2
    # Both attempts force JSON mode: dropping it made the model return an empty
    # completion, so the retry instead adds a short correction turn.
    for call in client.calls:
        assert call["response_format"] == {"type": "json_object"}
    assert "JSON" in client.calls[1]["messages"][-1]["content"]


def test_retry_delay_honours_server_hint() -> None:
    """A 429 sleeps as long as the server asked, not a fixed short backoff."""
    from app.services.llm_service import _retry_delay

    error = FakeStatusError(
        429,
        body={"error": {"message": "Please try again in 26.625s."}},
    )
    assert _retry_delay(error, 1) == 26.625

    header_error = FakeStatusError(429)
    header_error.response = SimpleNamespace(headers={"retry-after": "30"})
    assert _retry_delay(header_error, 1) == 30

    # A hint longer than the ceiling is clamped; a 429 without a hint falls back.
    capped = FakeStatusError(429, body={"error": {"message": "try again in 999s"}})
    assert _retry_delay(capped, 1) == llm_module.MAX_RATE_LIMIT_BACKOFF_SECONDS
    assert _retry_delay(FakeStatusError(429), 1) == llm_module.RATE_LIMIT_BACKOFF_SECONDS


@pytest.mark.asyncio
async def test_empty_completion_is_retried_then_succeeds() -> None:
    """An empty generation is retried rather than surfaced as a parse error."""
    service = LLMService()
    client = RecordingClient(["", '{"score": 5, "feedback": "fine"}'])
    service.client = client

    result = await service.generate_structured("Evaluate this", MockResponseSchema)

    assert result.score == 5
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_empty_completion_error_is_retryable() -> None:
    from app.services.llm_service import EmptyCompletionError, _is_retryable

    assert _is_retryable(EmptyCompletionError("no output"))


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
