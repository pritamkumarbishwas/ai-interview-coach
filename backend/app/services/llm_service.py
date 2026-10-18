import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import QuotaExceededError
from app.core.usage import record_llm_usage, usage_db
from app.repositories.llm_usage_repository import llm_usage_repository

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

REQUEST_TIMEOUT_SECONDS = 90.0
RETRY_BACKOFF_SECONDS = 1.0
# Cached monthly spend for the budget check (seconds).
SPEND_CACHE_SECONDS = 30.0
_spend_cache: tuple[float, float] | None = None
# Provider rate limits (tokens-per-minute windows) need a much longer pause
# than transient errors, or the retry just hits the same 429 again. The server
# usually states how long to wait ("try again in 26.6s"); that hint is honoured
# and only bounded by this ceiling.
RATE_LIMIT_BACKOFF_SECONDS = 12.0
MAX_RATE_LIMIT_BACKOFF_SECONDS = 90.0
# Failures worth trying again: timeouts, rate limits, server errors and
# unusable model output. Bad keys or bad requests fail identically every time.
RETRYABLE_STATUS_CODES = {408, 409, 429}


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM provider is missing or misconfigured."""


class EmptyCompletionError(RuntimeError):
    """Raised when the model returns no content at all (e.g. reasoning only)."""


async def _record_usage(provider: str, model: str, response: object) -> None:
    """Extract token counts from a completion and record them (best-effort)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        return
    try:
        await record_llm_usage(provider, model, prompt_tokens, completion_tokens)
    except Exception as exc:  # never let metering break a completion
        logger.warning("LLM usage recording failed: %s", exc)


async def _enforce_budget() -> None:
    """Block LLM calls once the month's estimated spend passes the ceiling.

    Best-effort and cheap: the spend rollup is cached for a short window so a
    burst of calls does not hammer the aggregation. With no budget configured,
    no usage context, or tracking disabled, this is a no-op.
    """
    budget = settings.monthly_llm_budget_usd
    if budget <= 0 or not settings.llm_cost_tracking_enabled:
        return
    db = usage_db.get()
    if db is None:
        return
    global _spend_cache
    now = time.monotonic()
    if _spend_cache is None or now - _spend_cache[1] > SPEND_CACHE_SECONDS:
        since = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        try:
            totals = await llm_usage_repository.totals(db, since)
        except Exception as exc:  # a metering failure must not block AI
            logger.warning("Could not read LLM spend for budget check: %s", exc)
            return
        _spend_cache = (totals["cost_usd"], now)
    spend = _spend_cache[0]
    if spend >= budget:
        raise QuotaExceededError(
            f"Monthly AI budget of ${budget:.2f} is exhausted "
            f"(estimated spend ${spend:.2f})"
        )


# Provider-side signals that the model emitted unusable JSON. Groq enforces
# `response_format=json_object` server-side and rejects a malformed generation
# with HTTP 400 `json_validate_failed` — a model-output problem, so a fresh
# sample (with a tighter instruction) is worth trying.
PROVIDER_JSON_ERROR_MARKERS = ("json_validate_failed", "Failed to validate JSON")


def _provider_rejected_json(error: Exception) -> bool:
    text = str(error)
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        text = f"{text} {body}"
    return any(marker in text for marker in PROVIDER_JSON_ERROR_MARKERS)


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, (ValidationError, EmptyCompletionError)):
        return True  # the model answered (or not at all), just not usable JSON
    if _provider_rejected_json(error):
        return True  # the model produced invalid JSON; resample
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code in RETRYABLE_STATUS_CODES or status_code >= 500
    return isinstance(error, APIError)  # connection-level failure, no status


_RETRY_HINT_PATTERN = re.compile(r"try again in ([\d.]+)\s*s", re.IGNORECASE)


def _server_retry_hint(error: Exception) -> float | None:
    """Seconds the provider explicitly asked us to wait before retrying."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        raw = headers.get("retry-after")
        if raw:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    text = f"{error} {getattr(error, 'body', '')}"
    match = _RETRY_HINT_PATTERN.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _retry_delay(error: Exception | None, attempt: int) -> float:
    """How long to wait before the next attempt.

    A fixed backoff is provably too short for token-per-minute windows (the
    server may ask for 27s while we would have waited 12s, re-tripping the same
    429), so a 429 honours the server's own hint, bounded so a buggy header
    cannot park the request forever. Other failures back off linearly.
    """
    if getattr(error, "status_code", None) == 429:
        hint = _server_retry_hint(error)
        if hint is not None:
            return min(max(hint, 1.0), MAX_RATE_LIMIT_BACKOFF_SECONDS)
        return RATE_LIMIT_BACKOFF_SECONDS
    return RETRY_BACKOFF_SECONDS * attempt


def _correction_hint(error: Exception) -> str:
    """A short, JSON-oriented correction for the next attempt.

    Deliberately avoids echoing the raw error: providers in strict JSON mode can
    regurgitate that text and fail to produce valid JSON (an empty generation).
    """
    if isinstance(error, ValidationError):
        missing = sorted(
            {
                str(err["loc"][0])
                for err in error.errors()
                if err.get("type") == "missing" and err.get("loc")
            }
        )
        detail = (
            f" It was missing required keys: {', '.join(missing)}." if missing else ""
        )
        return (
            "Your previous response was rejected by schema validation."
            f"{detail} Return ONLY valid JSON matching the schema exactly, "
            "including every required key (use an empty list for any section "
            "with no data)."
        )
    if isinstance(error, EmptyCompletionError):
        return (
            "Your previous response was empty. Return ONLY a single valid JSON "
            "object matching the schema, with every required key present."
        )
    return (
        "Your previous response was not valid JSON. Return ONLY a single valid "
        "JSON object matching the schema."
    )


class LLMService:
    """Thin wrapper around an OpenAI-compatible chat completions endpoint.

    The HTTP client is created lazily so importing the app never fails just
    because an API key is missing; the failure surfaces as a clear
    configuration error on the first call instead.
    """

    def __init__(self) -> None:
        self.provider = settings.llm_provider  # validated by `Settings`
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
            # The retry loop lives in `generate_structured`; letting the SDK
            # retry as well would multiply worst-case latency.
            max_retries=0,
        )

    async def generate_structured(self, prompt: str, schema: type[T], max_retries: int = 3) -> T:
        """Ask the model for JSON and validate it against `schema`.

        Invalid JSON / schema violations are fed back to the model; transient
        API failures are retried with a short backoff. After `max_retries`
        attempts the last error is raised.
        """
        # Refuse to spend past the configured monthly ceiling (Phase 9).
        await _enforce_budget()

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
                    {"role": "user", "content": _correction_hint(last_error)}
                )
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                raw_json = response.choices[0].message.content or ""

                # Tokens are spent whether or not the JSON validates, so record
                # usage as soon as the response arrives (best-effort).
                await _record_usage(self.provider, self.model, response)

                # Strip markdown code blocks if the LLM includes them
                raw_json = raw_json.strip()
                if not raw_json:
                    raise EmptyCompletionError(
                        "model returned no content for a JSON-mode request"
                    )
                if raw_json.startswith("```json"):
                    raw_json = raw_json[7:]
                elif raw_json.startswith("```"):
                    raw_json = raw_json[3:]
                if raw_json.endswith("```"):
                    raw_json = raw_json[:-3]
                raw_json = raw_json.strip()

                logger.debug("Raw LLM response: %s", raw_json)
                return schema.model_validate_json(raw_json)
            except LLMConfigurationError:
                raise  # no API key configured: retrying cannot help
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s: %s",
                    attempt,
                    max_retries,
                    type(exc).__name__,
                    exc,
                )
                if not _is_retryable(exc):
                    raise

            if attempt < max_retries:
                await asyncio.sleep(_retry_delay(last_error, attempt))

        assert last_error is not None
        raise last_error


llm_service = LLMService()
