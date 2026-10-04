"""Cross-cutting guarantees of the global error handlers (app/main.py).

Endpoint-level envelopes (401/404/409/422/503) are asserted next to their
features in test_auth/test_interviews/...; this file covers the handlers that
sit *between* features: framework errors, oversized bodies, unhandled bugs.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.main import app


def _with_temp_route(path: str, methods: list[str]):
    """Register a throwaway route for the duration of a test."""

    class ctx:
        route: APIRoute

    async def endpoint():
        if path == "/__boom":
            raise BadRequestError("Nope")
        if path == "/__crash":
            raise RuntimeError("unexpected bug")
        return {"ok": True}

    route = APIRoute(path=path, endpoint=endpoint, methods=methods)
    app.router.routes.append(route)
    ctx.route = route
    return ctx


def _remove_route(route: APIRoute) -> None:
    app.router.routes[:] = [r for r in app.router.routes if r is not route]


def test_method_not_allowed_uses_the_error_envelope(client: TestClient) -> None:
    response = client.post("/api/health")
    assert response.status_code == 405
    body = response.json()
    assert body["code"] == "method_not_allowed"
    assert isinstance(body["detail"], str)


def test_app_error_subclass_uses_the_error_envelope(client: TestClient) -> None:
    ctx = _with_temp_route("/__boom", ["GET"])
    try:
        response = client.get("/__boom")
    finally:
        _remove_route(ctx.route)
    assert response.status_code == 400
    assert response.json() == {"detail": "Nope", "code": "bad_request"}


def test_unhandled_exception_returns_500_envelope_without_stack_trace() -> None:
    ctx = _with_temp_route("/__crash", ["GET"])
    try:
        with TestClient(app, raise_server_exceptions=False) as crash_client:
            response = crash_client.get("/__crash")
    finally:
        _remove_route(ctx.route)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "code": "internal_error"}
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


def test_oversized_body_uses_the_error_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_body_bytes", 16)
    response = client.post(
        "/api/auth/register",
        json={"name": "x", "email": "a@b.co", "password": "supersecret123"},
    )
    assert response.status_code == 413
    assert response.json() == {
        "detail": "Request body exceeds the 0MB limit.",
        "code": "payload_too_large",
    }


def test_validation_error_detail_is_a_list(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/job-descriptions",
        headers=auth_headers,
        json={"raw_text": "missing the required title and company fields"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], list)
    assert body["detail"], "detail must list at least one field error"
    assert all(isinstance(item, dict) and "msg" in item for item in body["detail"])


def test_health_reports_degraded_when_the_database_is_unreachable(
    client: TestClient,
) -> None:
    saved = app.state.mongo
    app.state.mongo = None
    try:
        response = client.get("/api/health")
    finally:
        app.state.mongo = saved

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "environment": settings.environment,
        "database": "unreachable",
    }
