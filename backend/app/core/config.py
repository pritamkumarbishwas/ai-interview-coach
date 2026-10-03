from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-secret-change-me"
SUPPORTED_LLM_PROVIDERS = ("openai", "groq")

# <repo>/backend — the directory that owns the `app` package.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_storage_dir(raw: str | None = None) -> Path:
    """Return an absolute directory for uploaded files (created on demand)."""
    value = (raw or "").strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT / "data" / "resumes"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI Interview Coach"
    environment: str = Field(default="development")
    debug: bool = False
    api_prefix: str = "/api"
    log_level: str = "INFO"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "ai_interview_coach"

    # Absolute or relative path used to store uploaded resume files.
    # Relative paths are resolved against the backend package root, so the
    # default works both locally (<repo>/backend/data/resumes) and inside the
    # container (/app/data/resumes).
    storage_dir: str = "data/resumes"
    max_upload_bytes: int = 5 * 1024 * 1024
    # Rejected before the body is read, so a huge upload cannot exhaust memory.
    max_body_bytes: int = 10 * 1024 * 1024

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24

    # Login/register throttling (per client IP, per process).
    rate_limit_attempts: int = 20
    rate_limit_window_seconds: int = 60

    # Only enable when a reverse proxy in front of the app sets (and
    # overwrites) X-Forwarded-For. Trusting it from the open internet would
    # let clients pick their own rate-limit key.
    trust_proxy_headers: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    groq_api_key: str | None = None
    groq_model: str = "llama3-8b-8192"

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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

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
