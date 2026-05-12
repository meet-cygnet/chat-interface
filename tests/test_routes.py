"""Integration tests for the FastAPI routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.rate_limiter import TokenBucketRateLimiter
from backend.service import ChatService


@pytest.fixture()
def app():
    """Create a test FastAPI app with mocked dependencies."""
    app = create_app()
    # Override lifespan dependencies for testing.
    service = ChatService()
    # Manually set _client to None (simulating a service that hasn't started
    # its connection pool — good enough for health/validation tests).
    app.state.chat_service = service
    app.state.rate_limiter = TokenBucketRateLimiter(rate=1000, burst=1000)
    return app


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data


class TestChatEndpoint:
    def test_missing_messages_returns_422(self, client):
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422

    def test_empty_messages_returns_422(self, client):
        resp = client.post("/api/v1/chat", json={"messages": []})
        assert resp.status_code == 422

    def test_invalid_role_returns_422(self, client):
        resp = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "invalid", "content": "hi"}]},
        )
        assert resp.status_code == 422

    def test_temperature_out_of_range_returns_422(self, client):
        resp = client.post(
            "/api/v1/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 5.0,
            },
        )
        assert resp.status_code == 422


class TestRateLimiting:
    def test_rate_limit_returns_429(self, app):
        """When the rate limiter is exhausted, the endpoint returns 429."""
        # Set an extremely low rate limit.
        app.state.rate_limiter = TokenBucketRateLimiter(rate=0.001, burst=1)
        client = TestClient(app, raise_server_exceptions=False)

        # First request should succeed (or fail for other reasons, but not 429).
        resp1 = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        # Second request should hit rate limit.
        resp2 = client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "hi again"}]},
        )
        assert resp2.status_code == 429
        assert "Retry-After" in resp2.headers
