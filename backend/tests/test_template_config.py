"""Interview-template configuration scaffolding."""

import pytest
from pydantic import ValidationError

from app.models.template_config import InterviewTemplateConfig, RoundConfig


def test_template_config_defaults() -> None:
    config = InterviewTemplateConfig()
    assert config.proctoring_mode == "strict"
    assert config.integrity_policy == "advisory"
    assert config.allow_pauses is False
    assert len(config.rounds) == 1
    assert config.rounds[0].response_modes == ["voice", "typed"]


def test_template_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        InterviewTemplateConfig(unexpected=True)  # type: ignore[call-arg]


def test_round_config_enforces_bounds() -> None:
    with pytest.raises(ValidationError):
        RoundConfig(key="r", duration_minutes=0)
    with pytest.raises(ValidationError):
        RoundConfig(key="r", target_questions=50)
    with pytest.raises(ValidationError):
        RoundConfig(key="r", response_modes=["telepathy"])  # type: ignore[list-item]


def test_round_config_accepts_code_and_whiteboard_modes() -> None:
    round_ = RoundConfig(key="coding", response_modes=["code", "whiteboard"])
    assert round_.response_modes == ["code", "whiteboard"]
