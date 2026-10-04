import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-secret-change-me"
SUPPORTED_LLM_PROVIDERS = ("openai", "groq")

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
    environment: str = Field(default="development")
    debug: bool = False
    api_prefix: str = "/api"
    log_level: str = "INFO"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "ai_interview_coach"

    # Where uploaded resume files are stored (absolute, or relative to the
    # backend package root - see `resolve_storage_dir`).
    storage_dir: str = "data/resumes"
    max_upload_bytes: int = 5 * 1024 * 1024
    # Rejected before the body is read, so a huge upload cannot exhaust memory.
    max_body_bytes: int = 10 * 1024 * 1024

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24

    # Per-client-IP throttling (auth and AI-backed endpoints), per process.
    rate_limit_attempts: int = 20
    rate_limit_window_seconds: int = 60

    # Only enable when a reverse proxy in front of the app sets (and
    # overwrites) X-Forwarded-For. Trusting it from the open internet would
    # let clients pick their own rate-limit key.
    trust_proxy_headers: bool = False

    # Comma-separated list (`http://a,http://b`) or JSON array - both forms
    # are used in the shipped .env files, so parsing is left to the validator.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    groq_api_key: str | None = None
    groq_model: str = "llama3-8b-8192"

    # RAG: Qdrant vector store + local fastembed embeddings.
    # Switch off to compare question quality with and without retrieved context.
    rag_enabled: bool = True
    # http(s) URL talks to a Qdrant server (Docker container or Qdrant Cloud,
    # with QDRANT_API_KEY); any other value is passed to qdrant-client as an
    # embedded location — ":memory:" for tests or a directory for a
    # persistent local store without Docker.
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str = "data/models"
    # How many knowledge chunks each retrieval returns (spec: top 3-5).
    rag_top_k: int = Field(default=5, ge=3, le=5)
    # Markdown/JSON knowledge base ingested by scripts/ingest_knowledge_base.py.
    # Relative paths resolve against the backend package root.
    knowledge_base_dir: str = "../data/knowledge_base"

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
    """Return the absolute directory for uploaded files (created on demand).

    Relative values (the default `data/resumes`) resolve against the backend
    package root, so they work both locally (<repo>/backend/data/resumes) and
    inside the container (/app/data/resumes).
    """
    value = settings.storage_dir.strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT / "data" / "resumes"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def resolve_embedding_cache_dir() -> Path:
    """Where the fastembed ONNX model is downloaded (gitignored under backend/data)."""
    value = settings.embedding_cache_dir.strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT / "data" / "models"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def resolve_knowledge_base_dir() -> Path:
    """The knowledge base ingested by scripts/ingest_knowledge_base.py.

    Defaults to <repo>/data/knowledge_base (relative ../data/knowledge_base)
    but accepts an absolute path — docker-compose mounts the repo data
    directory at /knowledge_base and points KNOWLEDGE_BASE_DIR there.
    """
    value = settings.knowledge_base_dir.strip()
    path = Path(value).expanduser() if value else BACKEND_ROOT.parent / "data" / "knowledge_base"
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()
