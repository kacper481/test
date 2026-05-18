from __future__ import annotations

import uuid
from datetime import UTC, datetime

from opensearchpy import OpenSearch
from opentelemetry import trace

from common import chaos
from common import metrics as m

INDEX = "items"
MAPPINGS = {
    "properties": {
        "title": {"type": "text"},
        "description": {"type": "text"},
        "owner_id": {"type": "keyword"},
        "created_at": {"type": "date"},
    }
}

_tracer = trace.get_tracer(__name__)


def create_item(client: OpenSearch, title: str, description: str, owner_id: str) -> dict:
    with _tracer.start_as_current_span("items.create") as span:
        item_id = str(uuid.uuid4())
        doc = {
            "title": title,
            "description": description,
            "owner_id": owner_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        span.set_attribute("item.id", item_id)
        span.set_attribute("item.owner_id", owner_id)

        chaos.maybe_delay("CHAOS_OS_INDEX_SLOW_MS")
        client.index(index=INDEX, id=item_id, body=doc, refresh="wait_for")
        m.opensearch_ops.add(1, {"operation": "index", "index": INDEX})
        m.items_created.add(1)
        return {"id": item_id, **doc}


def get_item(client: OpenSearch, item_id: str) -> dict:
    with _tracer.start_as_current_span("items.get") as span:
        span.set_attribute("item.id", item_id)
        resp = client.get(index=INDEX, id=item_id)
        m.opensearch_ops.add(1, {"operation": "get", "index": INDEX})
        return {"id": resp["_id"], **resp["_source"]}


def search_items(client: OpenSearch, q: str | None, owner_id: str | None) -> dict:
    with _tracer.start_as_current_span("items.search") as span:
        span.set_attribute("search.query", q or "")
        if owner_id:
            span.set_attribute("item.owner_id", owner_id)

        must: list[dict] = []
        if q:
            must.append({"multi_match": {"query": q, "fields": ["title", "description"]}})
        if owner_id:
            must.append({"term": {"owner_id": owner_id}})

        body = {
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "aggs": {"by_owner": {"terms": {"field": "owner_id", "size": 10}}},
            "size": 50,
        }
        chaos.maybe_delay("CHAOS_ITEMS_SEARCH_MS")
        resp = client.search(index=INDEX, body=body)
        m.opensearch_ops.add(1, {"operation": "search", "index": INDEX})

        hits = [{"id": h["_id"], **h["_source"]} for h in resp["hits"]["hits"]]
        span.set_attribute("search.result_count", len(hits))
        m.search_result_size.record(len(hits))

        buckets = resp.get("aggregations", {}).get("by_owner", {}).get("buckets", [])
        return {
            "hits": hits,
            "total": resp["hits"]["total"]["value"],
            "by_owner": [{"owner_id": b["key"], "count": b["doc_count"]} for b in buckets],
        }
