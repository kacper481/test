"""Route-level tests for items-svc, users-svc, and gateway.

All OpenSearch and inter-service HTTP calls are mocked so no running
infrastructure is needed.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

OS_INFO = {"version": {"number": "2.13.0"}, "cluster_name": "test"}

ITEM_DOC = {
    "_id": "item-1",
    "_source": {
        "title": "hello",
        "description": "world",
        "owner_id": "user-1",
        "created_at": "2026-01-01T00:00:00+00:00",
    },
}

USER_DOC = {
    "_id": "user-1",
    "_source": {"name": "alice", "email": "alice@example.com", "created_at": "2026-01-01T00:00:00+00:00"},
}

SEARCH_RESP = {
    "hits": {
        "hits": [ITEM_DOC],
        "total": {"value": 1},
    },
    "aggregations": {"by_owner": {"buckets": [{"key": "user-1", "doc_count": 1}]}},
}

MGET_RESP = {"docs": [{**USER_DOC, "found": True}]}


def _make_os_mock() -> MagicMock:
    m = MagicMock()
    m.info.return_value = OS_INFO
    m.indices.exists.return_value = True     # skip index creation
    m.index.return_value = {"_id": "item-1", "result": "created"}
    m.get.side_effect = lambda index, id, **_: (
        ITEM_DOC if index == "items" else USER_DOC
    )
    m.search.return_value = SEARCH_RESP
    m.mget.return_value = MGET_RESP
    return m


# ---------------------------------------------------------------------------
# items-svc
# ---------------------------------------------------------------------------

@pytest.fixture()
def items_client():
    os_mock = _make_os_mock()
    with (
        patch("common.opensearch.make_client", return_value=os_mock),
        patch("common.opensearch.ensure_index"),
    ):
        import importlib
        import services.items_svc.main as m
        importlib.reload(m)
        app = m.create_app()
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_items_health(items_client):
    r = items_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_items_create(items_client):
    r = items_client.post(
        "/items", json={"title": "hello", "description": "world", "owner_id": "user-1"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "hello"
    assert "id" in body


def test_items_get(items_client):
    r = items_client.get("/items/item-1")
    assert r.status_code == 200
    assert r.json()["title"] == "hello"


def test_items_search(items_client):
    r = items_client.get("/items?q=hello")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["hits"]) == 1
    assert len(body["by_owner"]) == 1


def test_items_create_missing_owner(items_client):
    r = items_client.post("/items", json={"title": "x"})
    assert r.status_code == 422   # validation error: owner_id required


def test_items_get_not_found(items_client):
    from opensearchpy import NotFoundError

    with patch("services.items_svc.store.get_item", side_effect=NotFoundError(404, "not found", {})):
        r = items_client.get("/items/missing")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# users-svc
# ---------------------------------------------------------------------------

@pytest.fixture()
def users_client():
    os_mock = _make_os_mock()
    os_mock.index.return_value = {"_id": "user-1", "result": "created"}
    with (
        patch("common.opensearch.make_client", return_value=os_mock),
        patch("common.opensearch.ensure_index"),
    ):
        import importlib
        import services.users_svc.main as m
        importlib.reload(m)
        app = m.create_app()
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_users_health(users_client):
    r = users_client.get("/health")
    assert r.status_code == 200


def test_users_create(users_client):
    r = users_client.post("/users", json={"name": "alice", "email": "alice@example.com"})
    assert r.status_code == 201
    assert r.json()["name"] == "alice"


def test_users_create_no_email(users_client):
    r = users_client.post("/users", json={"name": "bob"})
    assert r.status_code == 201


def test_users_get(users_client):
    r = users_client.get("/users/user-1")
    assert r.status_code == 200
    assert r.json()["name"] == "alice"


def test_users_mget(users_client):
    r = users_client.post("/users/_mget", json={"ids": ["user-1"]})
    assert r.status_code == 200
    assert len(r.json()["users"]) == 1


def test_users_get_not_found(users_client):
    from opensearchpy import NotFoundError
    with patch("services.users_svc.store.get_user", side_effect=NotFoundError(404, "not found", {})):
        r = users_client.get("/users/missing")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# gateway
# ---------------------------------------------------------------------------

ITEM_RESP = {
    "id": "item-1",
    "title": "hello",
    "description": "world",
    "owner_id": "user-1",
    "created_at": "2026-01-01T00:00:00+00:00",
}

USER_RESP = {
    "id": "user-1",
    "name": "alice",
    "email": "alice@example.com",
    "created_at": "2026-01-01T00:00:00+00:00",
}

SEARCH_GW_RESP = {
    "hits": [ITEM_RESP],
    "total": 1,
    "by_owner": [{"owner_id": "user-1", "count": 1}],
}


def _gw_http_mock():
    """Return an async httpx mock whose get/post return canned responses."""
    import httpx

    def _resp(method: str, url: str, status: int, body) -> httpx.Response:
        # httpx.Response.raise_for_status() requires _request to be set
        req = httpx.Request(method, url)
        return httpx.Response(status_code=status, json=body, request=req)

    async def get(url: str, **kwargs):
        if "/health" in url:
            return _resp("GET", url, 200, {"status": "ok"})
        if "/users/" in url:
            return _resp("GET", url, 200, USER_RESP)
        if "/items/" in url:
            return _resp("GET", url, 200, ITEM_RESP)
        if "/items" in url:
            return _resp("GET", url, 200, SEARCH_GW_RESP)
        return _resp("GET", url, 404, {})

    async def post(url: str, **kwargs):
        if "/users" in url and "_mget" not in url:
            return _resp("POST", url, 201, USER_RESP)
        if "/users/_mget" in url:
            return _resp("POST", url, 200, {"users": [USER_RESP]})
        if "/items" in url:
            return _resp("POST", url, 201, ITEM_RESP)
        return _resp("POST", url, 404, {})

    mock = AsyncMock()
    mock.get = get
    mock.post = post
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture()
def gw_client():
    http_mock = _gw_http_mock()

    # Replace EventPublisher with a no-op so tests don't need RabbitMQ
    pub_mock = MagicMock()
    pub_mock.connect = AsyncMock()
    pub_mock.close = AsyncMock()
    pub_mock.publish = AsyncMock()

    with (
        patch("common.http_client.make_client", return_value=http_mock),
        patch("services.gateway.main.EventPublisher", return_value=pub_mock),
    ):
        import importlib
        import services.gateway.main as m
        importlib.reload(m)
        app = m.create_app()
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_gw_health(gw_client):
    r = gw_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["items_svc"]["status"] == "up"
    assert body["users_svc"]["status"] == "up"


def test_gw_create_user(gw_client):
    r = gw_client.post("/api/users", json={"name": "alice", "email": "alice@example.com"})
    assert r.status_code == 201
    assert r.json()["name"] == "alice"


def test_gw_get_user(gw_client):
    r = gw_client.get("/api/users/user-1")
    assert r.status_code == 200


def test_gw_create_item(gw_client):
    r = gw_client.post(
        "/api/items", json={"title": "hello", "description": "world", "owner_id": "user-1"}
    )
    assert r.status_code == 201
    assert r.json()["title"] == "hello"


def test_gw_get_item(gw_client):
    r = gw_client.get("/api/items/item-1")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "hello"
    assert body["owner"]["name"] == "alice"   # owner hydrated


def test_gw_search_items(gw_client):
    r = gw_client.get("/api/items?q=hello")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["hits"][0]["owner"]["name"] == "alice"   # owner hydrated


# ---------------------------------------------------------------------------
# chaos module
# ---------------------------------------------------------------------------

def test_chaos_delay_skipped_when_unset(monkeypatch):
    from common import chaos
    monkeypatch.delenv("CHAOS_TEST_DELAY", raising=False)
    import time
    start = time.monotonic()
    chaos.maybe_delay("CHAOS_TEST_DELAY")
    assert time.monotonic() - start < 0.01


def test_chaos_delay_sleeps_when_set(monkeypatch):
    from common import chaos
    monkeypatch.setenv("CHAOS_TEST_DELAY", "50")
    import time
    start = time.monotonic()
    chaos.maybe_delay("CHAOS_TEST_DELAY")
    assert time.monotonic() - start >= 0.04


def test_chaos_fail_at_100_percent(monkeypatch):
    from common import chaos
    from fastapi import HTTPException
    monkeypatch.setenv("CHAOS_TEST_FAIL", "1.0")
    with pytest.raises(HTTPException) as exc_info:
        chaos.maybe_fail("CHAOS_TEST_FAIL")
    assert exc_info.value.status_code == 500


def test_chaos_fail_at_zero_never_fires(monkeypatch):
    from common import chaos
    monkeypatch.setenv("CHAOS_TEST_FAIL", "0")
    for _ in range(20):
        chaos.maybe_fail("CHAOS_TEST_FAIL")  # must never raise
