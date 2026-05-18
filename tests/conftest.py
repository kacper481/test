"""Configure test environment — disable OTLP export so tests are silent."""

import os

# Point OTLP to a non-existent endpoint so exporters fail instantly
# rather than retrying with exponential backoff during tests.
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
os.environ.setdefault("OPENSEARCH_HOST", "http://localhost:9200")
os.environ.setdefault("ITEMS_SVC_URL", "http://localhost:8001")
os.environ.setdefault("USERS_SVC_URL", "http://localhost:8002")

# Suppress the OTel background-thread teardown noise that appears after the
# test process exits (PeriodicExportingMetricReader flushing to a dead endpoint).
import logging

logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)
