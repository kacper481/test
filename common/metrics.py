"""Custom OTel metrics exported via OTLP (scraped by Prometheus via the Collector).

The `FastAPIInstrumentor` already records standard HTTP server metrics. These
are the *business* metrics our app cares about.
"""

from __future__ import annotations

from opentelemetry import metrics

_meter = metrics.get_meter("app.business", schema_url="https://opentelemetry.io/schemas/1.11.0")


def _counter(name: str, description: str):
    return _meter.create_counter(name=name, description=description)


def _histogram(name: str, description: str, unit: str):
    return _meter.create_histogram(name=name, description=description, unit=unit)


items_created = _counter("items_created", "Total number of items created.")
users_created = _counter("users_created", "Total number of users created.")
opensearch_ops = _counter(
    "opensearch_operations",
    "OpenSearch operations performed, labeled by operation and index.",
)
search_result_size = _histogram(
    "search_result_size", "Number of hits returned by a search.", "hits"
)
notifications_sent = _counter("notifications_sent", "Async notifications processed by the worker.")
