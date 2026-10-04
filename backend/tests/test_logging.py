"""Structured logging: JSON formatter, format resolution, request middleware."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging import (
    JsonFormatter,
    resolve_log_format,
    setup_logging,
)


def make_record(
    message: str = "hello",
    level: int = logging.INFO,
    exc_info=None,
    **extra,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJsonFormatter:
    def test_emits_one_parseable_object_with_request_fields(self) -> None:
        record = make_record(
            "GET /api/health -> 200 (1.5ms)",
            request_id="abc123",
            method="GET",
            path="/api/health",
            status_code=200,
            duration_ms=1.5,
            client_ip="127.0.0.1",
        )
        payload = json.loads(JsonFormatter().format(record))

        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert payload["message"] == "GET /api/health -> 200 (1.5ms)"
        assert payload["ts"].endswith("+00:00")  # UTC ISO timestamp
        assert payload["request_id"] == "abc123"
        assert payload["status_code"] == 200
        assert payload["duration_ms"] == 1.5

    def test_omits_extras_that_were_not_provided(self) -> None:
        payload = json.loads(JsonFormatter().format(make_record()))
        assert "request_id" not in payload
        assert "status_code" not in payload
        assert set(payload) >= {"ts", "level", "logger", "message"}

    def test_includes_exception_text_when_present(self) -> None:
        try:
            raise ValueError("kaboom")
        except ValueError:
            import sys

            record = make_record("failed", exc_info=sys.exc_info())
        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError: kaboom" in payload["exception"]

    def test_unserialisable_promoted_field_falls_back_to_str(self) -> None:
        payload = json.loads(JsonFormatter().format(make_record(status_code=object())))
        assert isinstance(payload["status_code"], str)


class TestFormatResolution:
    def test_auto_is_text_outside_production(self) -> None:
        assert settings.environment != "production"
        assert resolve_log_format() == "text"

    def test_auto_is_json_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "environment", "production")
        assert resolve_log_format() == "json"

    def test_explicit_json_wins_over_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "log_format", "json")
        monkeypatch.setattr(settings, "environment", "development")
        assert resolve_log_format() == "json"


def test_setup_logging_swaps_the_formatter_in_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = settings.log_format
    try:
        monkeypatch.setattr(settings, "log_format", "json")
        setup_logging()
        root_handler = [h for h in logging.getLogger().handlers if getattr(h, "_aic_root", False)]
        assert root_handler, "setup_logging must install our root handler"
        assert isinstance(root_handler[0].formatter, JsonFormatter)

        monkeypatch.setattr(settings, "log_format", "text")
        setup_logging()
        root_handler = [h for h in logging.getLogger().handlers if getattr(h, "_aic_root", False)]
        assert not isinstance(root_handler[0].formatter, JsonFormatter)
    finally:
        settings.log_format = original
        setup_logging()


def test_request_middleware_logs_and_echoes_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get("/api/health")

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert set(request_id) <= set("0123456789abcdef")

    record = next(r for r in caplog.records if getattr(r, "request_id", None) == request_id)
    assert record.method == "GET"
    assert record.path == "/api/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0


def test_request_log_never_contains_authorization_material(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    token = f"secret-{uuid4().hex}"
    with caplog.at_level(logging.INFO, logger="app.main"):
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert token not in caplog.text
    assert "Authorization" not in caplog.text
