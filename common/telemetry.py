"""OpenTelemetry SDK bootstrap: traces + metrics + log correlation.

Called once per service at startup. After this, FastAPI, httpx, the `requests`
library (used by opensearch-py), and aio-pika all emit spans automatically;
metrics are exported via OTLP; log records get trace_id/span_id injected.

`app` may be None for non-FastAPI services (e.g. the notifications worker).
"""
from __future__ import annotations

import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_INITIALIZED = False


def configure_telemetry(app, service_name: str, otlp_endpoint: str) -> None:
    """Bootstrap OTel SDK. Pass `app=None` for non-FastAPI services."""
    global _INITIALIZED
    if not _INITIALIZED:
        resource = Resource.create({SERVICE_NAME: service_name})

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
        )
        trace.set_tracer_provider(tracer_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
            export_interval_millis=10_000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        HTTPXClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()  # opensearch-py uses requests under the hood
        LoggingInstrumentor().instrument(set_logging_format=False, log_level=logging.INFO)

        try:
            from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor
            AioPikaInstrumentor().instrument()
        except Exception:
            pass  # aio-pika instrumentation is optional

        _INITIALIZED = True

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
