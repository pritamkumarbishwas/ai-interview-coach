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
    # Public base URL of the SPA, used to build candidate magic links and staff
    # invitation links. It must match the origin the user actually opens.
    frontend_url: str = "http://localhost:3000"
    environment: str = Field(default="development")
    api_prefix: str = "/api"
    log_level: str = "INFO"
    # auto -> json in production, human-readable text elsewhere.
    log_format: str = "auto"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "ai_interview_coach"

    # Legacy local resume storage. New uploads live in GridFS; this remains so
    # pre-migration documents can still be downloaded.
    storage_dir: str = "data/resumes"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_body_bytes: int = 10 * 1024 * 1024

    # --- Resume content storage -------------------------------------------
    # Original files, full extracted content and page previews live in GridFS
    # so a resume document never approaches MongoDB's 16MB document limit.
    resume_bucket_name: str = "resume_files"
    resume_preview_bucket_name: str = "resume_previews"
    resume_preview_dpi: int = Field(default=144, ge=72, le=300)
    resume_max_previews: int = Field(default=40, ge=1, le=200)
    resume_max_pages: int = Field(default=60, ge=1, le=500)
    resume_max_inline_text_chars: int = Field(default=200_000, ge=10_000)
    resume_max_extraction_chunks: int = Field(default=40, ge=1, le=200)
    resume_extraction_chunk_chars: int = Field(default=7_000, ge=2_000, le=12_000)
    # Inline is the safe local-development default; Compose turns it off and
    # uses the durable background worker for OCR/LLM processing.
    resume_processing_inline: bool = True
    resume_ocr_enabled: bool = True
    resume_ocr_languages: str = "eng"
    resume_ocr_dpi: int = Field(default=200, ge=96, le=400)
    resume_ocr_min_chars: int = Field(default=40, ge=0)
    resume_ocr_timeout_seconds: int = Field(default=60, ge=5, le=300)
    tesseract_cmd: str = "tesseract"
    libreoffice_cmd: str = "soffice"
    resume_docx_preview_conversion: bool = True

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
        # Recruiter playback of a finalized session (occasional, not bulk).
        "recording_download": (30, 60),
        # Programmatic API clients poll; give them a generous budget.
        "public_api": (300, 60),
    }
    trust_proxy_headers: bool = False
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://resume-builder-rho-woad.vercel.app",
    ]

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"

    # --- LLM cost tracking (Phase 9) ---------------------------------------
    # Record token usage + estimated cost per call. Prices come from the price
    # book; override or add entries as "model=usd_per_1m_in:usd_per_1m_out".
    llm_cost_tracking_enabled: bool = True
    llm_pricing_overrides: Annotated[dict[str, tuple[float, float]], NoDecode] = {}

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

    # --- Registration mode ---------------------------------------------------
    # Screening deployments provision staff by invitation and let candidates
    # enter through magic links, so public self-registration is closed.
    feature_screening_enabled: bool = False

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

    # --- Data retention & erasure (Phase 9) --------------------------------
    # Candidate session data (interview + recording + proctoring) older than
    # this is destroyed by the retention purge. The invitation record is
    # anonymized, not deleted, so aggregate analytics survive.
    data_retention_days: int = Field(default=365, ge=30)
    # The purge only runs when explicitly triggered (admin endpoint or the
    # `retention.purge` background job); it is never destructive by accident.
    retention_purge_enabled: bool = False
    retention_batch_limit: int = Field(default=100, ge=1, le=1000)

    # --- Per-role limits (Phase 9) -----------------------------------------
    # Daily quotas per role and action, as "role:action=max" pairs separated by
    # semicolons, e.g. ROLE_LIMITS="recruiter:invitations=200;reviewer:exports=20".
    # `*` matches any role/action; a missing or 0 limit means unlimited.
    role_limits: Annotated[dict[str, int], NoDecode] = {}

    # --- Encryption at rest (Phase 9) --------------------------------------
    # Key used to encrypt app-managed secrets at rest (the ATS webhook signing
    # secret). Accepts a Fernet key (urlsafe base64) or any passphrase, which is
    # stretched to a key. When unset, secrets are stored in plaintext — only
    # acceptable for local development.
    field_encryption_key: str | None = None

    # --- Deployment residency & data-processing (Phase 9) ------------------
    # Region label surfaced in the compliance record (e.g. "eu-central-1"); the
    # platform makes no cross-region calls of its own besides the LLM provider.
    deployment_region: str = ""
    dpa_contact_email: str = ""

    # --- Seats & spend caps (Phase 9) --------------------------------------
    # Maximum provisioned staff accounts (0 = unlimited).
    max_staff_seats: int = Field(default=0, ge=0)
    # Monthly LLM spend ceiling in USD, checked before each LLM call
    # (0 = unlimited). Exceeding it blocks AI-backed endpoints.
    monthly_llm_budget_usd: float = Field(default=0.0, ge=0.0)

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

    @field_validator("role_limits", mode="before")
    @classmethod
    def _parse_role_limits(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return {}
        limits: dict[str, int] = {}
        for pair in text.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise ValueError(
                    "ROLE_LIMITS entries must look like 'role:action=max_per_day'"
                )
            key, _, raw_max = pair.partition("=")
            if ":" not in key:
                raise ValueError(f"ROLE_LIMITS entry {pair!r} must name a 'role:action'")
            try:
                limits[key.strip().lower()] = int(raw_max)
            except ValueError as exc:
                raise ValueError(
                    f"ROLE_LIMITS entry {pair!r} has a non-integer limit"
                ) from exc
        return limits

    @field_validator("llm_pricing_overrides", mode="before")
    @classmethod
    def _parse_llm_pricing_overrides(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return {}
        overrides: dict[str, tuple[float, float]] = {}
        for pair in text.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise ValueError(
                    "LLM_PRICING_OVERRIDES entries must look like "
                    "'model=usd_per_1m_in:usd_per_1m_out'"
                )
            model, _, spec = pair.partition("=")
            parts = spec.split(":")
            if len(parts) != 2:
                raise ValueError(
                    f"LLM_PRICING_OVERRIDES entry {pair!r} must provide input and "
                    "output prices"
                )
            try:
                overrides[model.strip()] = (float(parts[0]), float(parts[1]))
            except ValueError as exc:
                raise ValueError(
                    f"LLM_PRICING_OVERRIDES entry {pair!r} has non-numeric prices"
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
