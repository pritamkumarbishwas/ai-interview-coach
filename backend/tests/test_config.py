import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_JWT_SECRET, Settings


def test_cors_origins_accepts_comma_separated_list() -> None:
    settings = Settings(cors_origins="http://localhost:3000, http://localhost:5173")
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]


def test_cors_origins_accepts_json_array() -> None:
    settings = Settings(cors_origins='["http://localhost:3000", "http://localhost:5173"]')
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]


def test_invalid_llm_provider_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="LLM_PROVIDER"):
        Settings(llm_provider="mock")


def test_production_requires_a_real_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(environment="production", jwt_secret=DEFAULT_JWT_SECRET)


def test_production_rejects_wildcard_cors_origin() -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            jwt_secret="a-long-random-secret",
            cors_origins="*",
        )


def test_environment_helpers() -> None:
    assert Settings(environment="production").is_production
    assert Settings(environment="test").is_test
    assert not Settings(environment="development").is_production
