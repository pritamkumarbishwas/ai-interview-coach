"""Rate limiting: budget headers, scope isolation, window expiry, test no-op."""

from __future__ import annotations

import time
from collections import deque
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import rate_limit as rate_limit_module
from app.core.config import settings
from app.core.rate_limit import client_key


@pytest.fixture()
def limiter_on(monkeypatch: pytest.MonkeyPatch):
    """Switch throttling on (it is off for the suite) with a budget of 3."""
    monkeypatch.setattr(rate_limit_module.settings, "environment", "development")
    monkeypatch.setattr(rate_limit_module._limiter, "max_hits", 3)
    yield rate_limit_module._limiter
    rate_limit_module._limiter._hits.clear()


def _login_attempts(client: TestClient, email: str, count: int) -> list:
    payload = {"email": email, "password": "wrong-password"}
    return [client.post("/api/auth/login", json=payload) for _ in range(count)]


def test_blocked_requests_carry_throttle_headers(
    client: TestClient, registered_user: dict, limiter_on
) -> None:
    responses = _login_attempts(client, registered_user["email"], 4)
    assert [r.status_code for r in responses[:3]] == [401, 401, 401]

    throttled = responses[3]
    assert throttled.status_code == 429
    assert throttled.json() == {
        "detail": "Too many requests, please try again later.",
        "code": "rate_limited",
    }
    assert int(throttled.headers["Retry-After"]) >= 1
    assert throttled.headers["X-RateLimit-Limit"] == "3"
    assert throttled.headers["X-RateLimit-Remaining"] == "0"


def test_allowed_requests_advertise_the_limit(client: TestClient, limiter_on) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Throttle Check",
            "email": f"rl.{uuid4().hex[:10]}@example.com",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["X-RateLimit-Limit"] == "3"


def test_scopes_do_not_leak_into_each_other(
    client: TestClient, registered_user: dict, limiter_on
) -> None:
    """Exhausting the login scope must not throttle registration."""
    responses = _login_attempts(client, registered_user["email"], 4)
    assert responses[3].status_code == 429

    register = client.post(
        "/api/auth/register",
        json={
            "name": "Other Scope",
            "email": f"other.{uuid4().hex[:10]}@example.com",
            "password": "supersecret123",
        },
    )
    assert register.status_code == 201, register.text


def test_expired_window_allows_requests_again(
    client: TestClient, registered_user: dict, limiter_on
) -> None:
    responses = _login_attempts(client, registered_user["email"], 4)
    assert responses[3].status_code == 429

    # Age every recorded hit past the window — the budget is replenished.
    aged = time.monotonic() - (limiter_on.window_seconds + 5)
    for key in list(limiter_on._hits):
        limiter_on._hits[key] = deque([aged])

    retried = _login_attempts(client, registered_user["email"], 1)
    assert retried[0].status_code == 401


def test_throttling_is_a_noop_in_the_test_environment(client: TestClient) -> None:
    """ENVIRONMENT=test must never throttle, no matter how many requests."""
    assert settings.is_test
    for _ in range(settings.rate_limit_attempts + 5):
        response = client.post("/api/auth/register", json={})
        assert response.status_code == 422
        assert response.headers.get("X-RateLimit-Limit") is None


def test_client_key_honours_forwarded_for_only_when_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def make(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (host, 1234),
            "method": "GET",
            "path": "/",
            "query_string": b"",
        }
        return Request(scope)

    forwarded = make({"x-forwarded-for": "9.9.9.9, 1.1.1.1"})

    monkeypatch.setattr(rate_limit_module.settings, "trust_proxy_headers", True)
    assert client_key(forwarded) == "9.9.9.9"

    monkeypatch.setattr(rate_limit_module.settings, "trust_proxy_headers", False)
    assert client_key(forwarded) == "10.0.0.1"
