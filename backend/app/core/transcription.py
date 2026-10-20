"""Server-side speech-to-text (STT) for candidate answers.

The browser Web Speech API covers Chromium only, so a server transcriber is the
portable path for Safari/Firefox (and for accents/languages Web Speech mangles).
Like :mod:`app.core.mailer`, this is a provider-agnostic seam: the default
``none`` provider keeps the feature off, and ``openai``/``groq`` share the LLM
provider keys. Adding a provider means implementing :class:`Transcriber`,
registering the name in ``SUPPORTED_TRANSCRIPTION_PROVIDERS`` and extending
:func:`build_transcriber`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from openai import AsyncOpenAI

from app.core.config import SUPPORTED_TRANSCRIPTION_PROVIDERS, settings
from app.core.exceptions import (
    FeatureUnavailableError,
    ServiceUnavailableError,
    UnsupportedMediaTypeError,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 90.0
ALLOWED_AUDIO_CONTENT_TYPES = (
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-m4a",
)


def normalize_audio_content_type(content_type: str) -> str:
    """Drop codec parameters (``audio/webm;codecs=opus`` -> ``audio/webm``)."""
    return content_type.split(";", 1)[0].strip().lower()


class TranscriptionError(RuntimeError):
    """Raised when a transcriber call fails (transport or provider error)."""


class Transcriber(ABC):
    """Transport seam: everything that needs STT depends on this."""

    @abstractmethod
    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        """Return the transcript text for ``audio`` (``""`` when silent)."""


class NullTranscriber(Transcriber):
    """Default provider: server STT is disabled."""

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        raise FeatureUnavailableError(
            "Server-side transcription is not configured on this deployment."
        )


class OpenAICompatibleTranscriber(Transcriber):
    """Whisper-style transcription over an OpenAI-compatible endpoint."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.model = settings.transcription_model
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
            raise ServiceUnavailableError(
                f"{missing} must be set when TRANSCRIPTION_PROVIDER={self.provider!r}."
            )
        return AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1
        )

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        if not audio:
            return ""
        base_type = normalize_audio_content_type(content_type)
        if base_type not in ALLOWED_AUDIO_CONTENT_TYPES:
            raise UnsupportedMediaTypeError("Unsupported audio content type.")
        try:
            response = await self.client.audio.transcriptions.create(
                model=self.model,
                file=(filename or "answer.webm", audio, base_type),
            )
        except Exception as exc:  # provider/transport failure
            logger.warning("Transcription failed provider=%s: %s", self.provider, exc)
            raise ServiceUnavailableError("Transcription is temporarily unavailable.") from exc
        text = getattr(response, "text", "") or ""
        return text.strip()


def build_transcriber(provider: str | None = None) -> Transcriber:
    """Construct the transcriber for ``provider`` (defaults to the configured one)."""
    choice = (provider or settings.transcription_provider).strip().lower()
    if choice == "none":
        return NullTranscriber()
    if choice in ("openai", "groq"):
        return OpenAICompatibleTranscriber(choice)
    raise ValueError(
        f"Unsupported TRANSCRIPTION_PROVIDER={choice!r}. "
        f"Valid options: {', '.join(SUPPORTED_TRANSCRIPTION_PROVIDERS)}."
    )


def get_transcriber() -> Transcriber:
    """The application-wide transcriber (built once from settings)."""
    return _transcriber


_transcriber: Transcriber = build_transcriber()
