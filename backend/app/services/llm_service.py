import asyncio
import json
import logging
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

VALID_PROVIDERS = ("openai", "groq")
REQUEST_TIMEOUT_SECONDS = 90.0
RETRY_BACKOFF_SECONDS = 1.0


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM provider is missing or misconfigured."""


class LLMService:
    """Thin wrapper around an OpenAI-compatible chat completions endpoint.

    The HTTP client is created lazily so importing the app never fails just
    because an API key is missing; the failure surfaces as a clear
    configuration error on the first call instead.
    """

    def __init__(self) -> None:
        self.provider = settings.llm_provider.strip().lower()
        if self.provider not in VALID_PROVIDERS:
            raise LLMConfigurationError(
                f"LLM_PROVIDER={self.provider!r} is not supported. "
                f"Valid options: {', '.join(VALID_PROVIDERS)}."
            )
        self.model = settings.groq_model if self.provider == "groq" else settings.openai_model
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    @client.setter
    def client(self, value: AsyncOpenAI) -> None:
        self._client = value

    def _build_client(self) -> AsyncOpenAI:
        if self.provider == "groq":
            api_key = settings.groq_api_key
            missing = "GROQ_API_KEY"
            base_url = "https://api.groq.com/openai/v1"
        else:
            api_key = settings.openai_api_key
            missing = "OPENAI_API_KEY"
            base_url = None

        if not api_key:
            raise LLMConfigurationError(
                f"{missing} must be set when LLM_PROVIDER={self.provider!r}."
            )

        logger.info("Initializing LLM client provider=%s model=%s", self.provider, self.model)
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=2,
        )

    async def generate_structured(self, prompt: str, schema: type[T], max_retries: int = 3) -> T:
        """Ask the model for JSON and validate it against `schema`.

        Invalid JSON / schema violations are fed back to the model; transient
        API failures are retried with a short backoff. After `max_retries`
        attempts the last error is raised.
        """
        system_prompt = (
            "You are a helpful AI assistant. You must respond in ONLY valid JSON.\n"
            f"The JSON must strictly match the following schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            logger.info(
                "generate_structured attempt %d/%d provider=%s model=%s",
                attempt,
                max_retries,
                self.provider,
                self.model,
            )
            messages = list(base_messages)
            if last_error is not None:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your last response failed validation with the "
                            f"following error:\n{last_error}\n\n"
                            "Return corrected JSON only."
                        ),
                    }
                )
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                raw_json = response.choices[0].message.content or ""
                logger.debug("Raw LLM response: %s", raw_json)
                return schema.model_validate_json(raw_json)
            except ValidationError as exc:
                last_error = exc
                logger.warning("Validation error on attempt %d/%d: %s", attempt, max_retries, exc)
            except APIError as exc:
                last_error = exc
                logger.warning("LLM API error on attempt %d/%d: %s", attempt, max_retries, exc)
            except Exception as exc:
                last_error = exc
                logger.error("Unexpected error during LLM generation: %s", exc)

            if attempt < max_retries:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        assert last_error is not None
        raise last_error


llm_service = LLMService()
