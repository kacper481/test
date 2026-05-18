"""Custom OTel metrics exported via OTLP (scraped by Prometheus via the Collector).

The `FastAPIInstrumentor` already records standard HTTP server metrics. These
are the *business* metrics our app cares about.
"""
from __future__ import annotations

from opentelemetry import metrics


_meter = metrics.get_meter("app.business")

items_created = _meter.create_counter(
    name="items_created_total",
    description="Total number of items created.",
)

users_created = _meter.create_counter(
    name="users_created_total",
    description="Total number of users created.",
)

opensearch_ops = _meter.create_counter(
    name="opensearch_operations_total",
    description="OpenSearch operations performed, labeled by operation and index.",
)

search_result_size = _meter.create_histogram(
    name="search_result_size",
    description="Number of hits returned by a search.",
    unit="hits",
)
