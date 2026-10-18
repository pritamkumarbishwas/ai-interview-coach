"""Feature flags and interview-template configuration scaffolding."""

import pytest
from pydantic import ValidationError

from app.core.features import FLAG_NAMES, FeatureFlags, load_features
from app.models.template_config import InterviewTemplateConfig, RoundConfig


def test_feature_flags_default_to_off() -> None:
    assert FeatureFlags().as_dict() == {name: False for name in FLAG_NAMES}


def test_is_enabled_and_unknown_flag() -> None:
    flags = FeatureFlags(screening=True, magic_links=False)
    assert flags.is_enabled("screening") is True
    assert flags.is_enabled("magic_links") is False
    with pytest.raises(KeyError):
        flags.is_enabled("does_not_exist")


def test_load_features_reflects_settings_defaults() -> None:
    # Nothing enables these flags in the test environment.
    assert load_features().as_dict() == {name: False for name in FLAG_NAMES}


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
