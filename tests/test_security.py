"""Tests for the opt-in auth + rate-limiting features."""

from __future__ import annotations

import importlib
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient


@contextmanager
def _build_gateway(monkeypatch, env: dict[str, str]):
    """Yield a TestClient for a fresh gateway built under the given env.

    All downstream deps are mocked. The patches stay active for the lifetime of
    the TestClient (including lifespan startup/shutdown), so no real RabbitMQ or
    HTTP connections are ever attempted.
    """
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    http_mock = AsyncMock()

    async def _ok(url: str, **kwargs):
        return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))

    http_mock.get = _ok
    http_mock.aclose = AsyncMock()

    pub_mock = MagicMock()
    pub_mock.connect = AsyncMock()
    pub_mock.close = AsyncMock()
    pub_mock.publish = AsyncMock()

    with (
        patch("common.http_client.make_client", return_value=http_mock),
        patch("services.gateway.main.EventPublisher", return_value=pub_mock),
    ):
        import services.gateway.main as gw_main

        importlib.reload(gw_main)
        app = gw_main.create_app()
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client


# ---------------------------------------------------------------------------
# API key auth
# ---------------------------------------------------------------------------


def test_auth_disabled_when_key_unset(monkeypatch):
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    with _build_gateway(monkeypatch, {}) as c:
        r = c.get("/api/users/abc")
        assert r.status_code == 200  # reaches route; downstream mock returns 200


def test_auth_rejects_missing_header(monkeypatch):
    with _build_gateway(monkeypatch, {"GATEWAY_API_KEY": "secret"}) as c:
        r = c.get("/api/users/abc")
        assert r.status_code == 401
        assert "X-API-Key" in r.headers.get("WWW-Authenticate", "")


def test_auth_rejects_wrong_key(monkeypatch):
    with _build_gateway(monkeypatch, {"GATEWAY_API_KEY": "secret"}) as c:
        r = c.get("/api/users/abc", headers={"X-API-Key": "wrong"})
        assert r.status_code == 403


def test_auth_accepts_correct_key(monkeypatch):
    with _build_gateway(monkeypatch, {"GATEWAY_API_KEY": "secret"}) as c:
        r = c.get("/api/users/abc", headers={"X-API-Key": "secret"})
        assert r.status_code == 200


def test_health_endpoint_unauthenticated(monkeypatch):
    """/health must stay open even when auth is on (liveness probes)."""
    with _build_gateway(monkeypatch, {"GATEWAY_API_KEY": "secret"}) as c:
        r = c.get("/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    with _build_gateway(monkeypatch, {}) as c:
        for _ in range(15):
            assert c.get("/health").status_code == 200


def test_rate_limit_enforces_429(monkeypatch):
    with _build_gateway(monkeypatch, {"RATE_LIMIT_PER_MINUTE": "5"}) as c:
        statuses = [c.get("/health").status_code for _ in range(10)]
        assert statuses.count(200) == 5
        assert statuses.count(429) == 5
