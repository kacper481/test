"""Thin wrapper around `opensearch-py` with index-bootstrap helper.

Note: `requests` instrumentation (set up in `common.telemetry`) automatically
creates child spans for every OpenSearch HTTP call — no manual tracing here.
"""
from __future__ import annotations

from urllib.parse import urlparse

from opensearchpy import OpenSearch


def make_client(host_url: str) -> OpenSearch:
    parsed = urlparse(host_url)
    return OpenSearch(
        hosts=[{"host": parsed.hostname or "localhost", "port": parsed.port or 9200}],
        use_ssl=parsed.scheme == "https",
        verify_certs=False,
        ssl_show_warn=False,
    )


def ensure_index(client: OpenSearch, index: str, mappings: dict) -> None:
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body={"mappings": mappings})
