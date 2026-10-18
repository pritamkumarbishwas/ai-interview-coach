import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-secret-change-me"
SUPPORTED_LLM_PROVIDERS = ("openai", "groq")
# Only the console provider ships today; real transport providers (e.g. smtp)
# slot in here without touching call sites.
SUPPORTED_MAIL_PROVIDERS = ("console",)
# Server-side speech-to-text ("none" disables it; the browser Web Speech API is
# then the only transcription path). openai/groq share the LLM provider keys.
SUPPORTED_TRANSCRIPTION_PROVIDERS = ("none", "openai", "groq")

# <repo>/backend — the directory that owns the `app` package.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Interview Coach"
    # Public base URL of the SPA — used to build links in outbound emails
    # (staff invitations now; candidate magic links in a later phase).
    frontend_url: str = "http://localhost:5173"
    environment: str = Field(default="development")
    debug: bool = False
    api_prefix: str = "/api"
    log_level: str = "INFO"
    # auto -> json in production, human-readable text elsewhere.
    log_format: str = "auto"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "ai_interview_coach"

    storage_dir: str = "data/resumes"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_body_bytes: int = 10 * 1024 * 1024

    # Interview session recordings (GridFS). Chunked upload: each chunk is
    # capped, and the total per-kind recording is capped to bound storage.
    max_recording_chunk_bytes: int = 16 * 1024 * 1024
    max_recording_bytes: int = 500 * 1024 * 1024
    recording_bucket_name: str = "interview_recordings"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24

    rate_limit_attempts: int = 20
    rate_limit_window_seconds: int = 60
    # Per-scope overrides as "scope=max_hits:window_seconds" pairs separated
    # by semicolons, e.g. RATE_LIMIT_OVERRIDES="recording_upload=60:60".
    # Bulk authenticated endpoints (chunked recording uploads) need a higher
    # budget than the global credential-stuffing guard. The default gives
    # recording uploads ~60/min (steady-state is ~6/min at a 10s timeslice,
    # plus headroom for retries).
    rate_limit_overrides: Annotated[dict[str, tuple[int, int]], NoDecode] = {
        "recording_upload": (60, 60),
        # Guest (token) screening uploads/transcription: same steady-state
        # profile as authenticated recording, so the same headroom applies.
        "screening_recording": (60, 60),
        "screening_transcribe": (60, 60),
    }
    trust_proxy_headers: bool = False
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "https://resume-builder-rho-woad.vercel.app"]

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"

    # --- Server-side transcription (speech-to-text) ------------------------
    # "none" disables server STT; candidates then rely on the browser Web
    # Speech API (Chromium only). openai/groq reuse the LLM API keys above.
    transcription_provider: str = "none"
    transcription_model: str = "whisper-1"

    rag_enabled: bool = True
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str = "data/models"
    rag_top_k: int = Field(default=5, ge=3, le=5)
    knowledge_base_dir: str = "../data/knowledge_base"

    # --- Outbound email ----------------------------------------------------
    # "console" logs the message instead of sending it — safe default so no
    # email leaves the process until a real provider is configured.
    mail_provider: str = "console"
    mail_from: str = "no-reply@example.com"
    mail_from_name: str = "AI Interview Coach"

    # --- Background jobs ---------------------------------------------------
    # The worker is opt-in: the queue and its storage are always available, but
    # nothing polls for jobs unless this is enabled (or a worker is started in
    # code, as tests do).
    jobs_enabled: bool = False
    jobs_collection_name: str = "background_jobs"
    jobs_poll_interval_seconds: float = Field(default=5.0, gt=0)
    jobs_max_attempts: int = Field(default=3, ge=1)
    jobs_backoff_seconds: float = Field(default=30.0, gt=0)

    # --- Feature flags (staged rollout of the screening platform) -----------
    feature_screening_enabled: bool = False
    feature_magic_links_enabled: bool = False
    feature_proctoring_integrity_enabled: bool = False

    # --- Staff bootstrap ---------------------------------------------------
    # Optional seed admin, created on startup when set. This is how a fresh
    # single-company deployment gets its first privileged account (public
    # registration is disabled once screening is enabled).
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Admin"

    # --- Candidate invitations ---------------------------------------------
    # Default magic-link lifetime; can be overridden per invitation.
    invitation_ttl_days: int = Field(default=7, ge=1, le=30)

    @field_validator("log_format", mode="before")
    @classmethod
    def _validate_log_format(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        choice = value.strip().lower()
        if choice not in ("auto", "text", "json"):
            raise ValueError(
                f"LOG_FORMAT={value!r} is not supported. Valid options: auto, text, json."
            )
        return choice

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _validate_llm_provider(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        provider = value.strip().lower()
        if provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(
                f"LLM_PROVIDER={value!r} is not supported. "
                f"Valid options: {', '.join(SUPPORTED_LLM_PROVIDERS)}."
            )
        return provider

    @field_validator("mail_provider", mode="before")
    @classmethod
    def _validate_mail_provider(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        provider = value.strip().lower()
        if provider not in SUPPORTED_MAIL_PROVIDERS:
            raise ValueError(
                f"MAIL_PROVIDER={value!r} is not supported. "
                f"Valid options: {', '.join(SUPPORTED_MAIL_PROVIDERS)}."
            )
        return provider

    @field_validator("transcription_provider", mode="before")
    @classmethod
    def _validate_transcription_provider(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        provider = value.strip().lower()
        if provider not in SUPPORTED_TRANSCRIPTION_PROVIDERS:
            raise ValueError(
                f"TRANSCRIPTION_PROVIDER={value!r} is not supported. "
                f"Valid options: {', '.join(SUPPORTED_TRANSCRIPTION_PROVIDERS)}."
            )
        return provider

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("CORS_ORIGINS is not a valid JSON array") from exc
            if not isinstance(parsed, list):
                raise ValueError("CORS_ORIGINS must be a list of origins")
            return parsed
        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @field_validator("rate_limit_overrides", mode="before")
    @classmethod
    def _parse_rate_limit_overrides(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return {}
        overrides: dict[str, tuple[int, int]] = {}
        for pair in text.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise ValueError(
                    "RATE_LIMIT_OVERRIDES entries must look like "
                    "'scope=max_hits:window_seconds'"
                )
            scope, _, spec = pair.partition("=")
            parts = spec.split(":")
            if len(parts) != 2:
                raise ValueError(
                    f"RATE_LIMIT_OVERRIDES entry {pair!r} must provide "
                    "max_hits and window_seconds"
                )
            try:
                overrides[scope.strip()] = (int(parts[0]), int(parts[1]))
            except ValueError as exc:
                raise ValueError(
                    f"RATE_LIMIT_OVERRIDES entry {pair!r} has non-integer limits"
                ) from exc
        return overrides

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.is_production:
            if self.jwt_secret == DEFAULT_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set to a strong value in production")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not contain '*' in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def is_test(self) -> bool:
        return self.environment.strip().lower() == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def resolve_storage_dir() -> Path:
    value = settings.storage_dir.strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT / "data" / "resumes"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def resolve_embedding_cache_dir() -> Path:
    value = settings.embedding_cache_dir.strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT / "data" / "models"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def resolve_knowledge_base_dir() -> Path:
    value = settings.knowledge_base_dir.strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT.parent / "data" / "knowledge_base"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()
