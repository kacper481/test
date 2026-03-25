import os
import uuid
from typing import Optional

from opensearchpy import OpenSearch, NotFoundError

INDEX = "items"

INDEX_MAPPINGS = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "description": {"type": "text"},
            "created_at": {"type": "date"},
        }
    }
}


def _get_client() -> OpenSearch:
    host = os.getenv("OPENSEARCH_HOST", "http://localhost:9200")
    # Strip scheme for the OpenSearch client constructor
    host = host.replace("http://", "").replace("https://", "")
    return OpenSearch(
        hosts=[{"host": host.split(":")[0], "port": int(host.split(":")[1])}],
        use_ssl=False,
        verify_certs=False,
    )


client: OpenSearch = _get_client()


def ensure_index() -> None:
    if not client.indices.exists(INDEX):
        client.indices.create(index=INDEX, body=INDEX_MAPPINGS)


def create_item(title: str, description: str) -> dict:
    from datetime import datetime, timezone

    doc = {
        "title": title,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    item_id = str(uuid.uuid4())
    client.index(index=INDEX, id=item_id, body=doc, refresh="wait_for")
    return {"id": item_id, **doc}


def get_item(item_id: str) -> dict:
    resp = client.get(index=INDEX, id=item_id)
    return {"id": resp["_id"], **resp["_source"]}


def search_items(q: Optional[str] = None) -> list[dict]:
    if q:
        query = {
            "query": {
                "multi_match": {
                    "query": q,
                    "fields": ["title", "description"],
                }
            }
        }
    else:
        query = {"query": {"match_all": {}}}

    resp = client.search(index=INDEX, body=query)
    return [{"id": hit["_id"], **hit["_source"]} for hit in resp["hits"]["hits"]]
