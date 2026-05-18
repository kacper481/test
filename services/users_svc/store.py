from __future__ import annotations

import uuid
from datetime import datetime, timezone

from opensearchpy import OpenSearch
from opentelemetry import trace

from common import metrics as m

INDEX = "users"
MAPPINGS = {
    "properties": {
        "name": {"type": "text"},
        "email": {"type": "keyword"},
        "created_at": {"type": "date"},
    }
}

_tracer = trace.get_tracer(__name__)


def create_user(client: OpenSearch, name: str, email: str | None) -> dict:
    with _tracer.start_as_current_span("users.create") as span:
        user_id = str(uuid.uuid4())
        doc = {
            "name": name,
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        span.set_attribute("user.id", user_id)
        client.index(index=INDEX, id=user_id, body=doc, refresh="wait_for")
        m.opensearch_ops.add(1, {"operation": "index", "index": INDEX})
        m.users_created.add(1)
        return {"id": user_id, **doc}


def get_user(client: OpenSearch, user_id: str) -> dict:
    with _tracer.start_as_current_span("users.get") as span:
        span.set_attribute("user.id", user_id)
        resp = client.get(index=INDEX, id=user_id)
        m.opensearch_ops.add(1, {"operation": "get", "index": INDEX})
        return {"id": resp["_id"], **resp["_source"]}


def mget_users(client: OpenSearch, ids: list[str]) -> list[dict]:
    with _tracer.start_as_current_span("users.mget") as span:
        span.set_attribute("user.id_count", len(ids))
        if not ids:
            return []
        resp = client.mget(index=INDEX, body={"ids": ids})
        m.opensearch_ops.add(1, {"operation": "mget", "index": INDEX})
        return [
            {"id": doc["_id"], **doc["_source"]}
            for doc in resp["docs"]
            if doc.get("found")
        ]
