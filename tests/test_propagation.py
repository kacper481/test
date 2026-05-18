"""Tests for distributed trace context propagation through RabbitMQ.

These cover the *interesting* mechanism — that `propagate.inject` in the
publisher and `propagate.extract` in the worker keep one logical trace
intact across a message-queue boundary. If these regress, distributed
traces in Jaeger will silently break into per-service fragments.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture(scope="module")
def span_exporter():
    """Module-scoped InMemorySpanExporter set up against a fresh TracerProvider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


# ---------------------------------------------------------------------------
# Publisher: inject the current trace context into message headers
# ---------------------------------------------------------------------------


def test_publisher_injects_active_trace_into_headers(span_exporter):
    """Calling publish() inside a span must write traceparent matching that trace_id."""
    from services.gateway.events import EventPublisher

    pub = EventPublisher("amqp://localhost")
    captured: dict = {}

    async def _fake_publish(message, routing_key=None):
        captured["headers"] = dict(message.headers or {})
        captured["routing_key"] = routing_key
        captured["body"] = message.body

    pub._exchange = MagicMock()
    pub._exchange.publish = _fake_publish

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("POST /api/items") as parent:
        parent_trace_id = f"{parent.get_span_context().trace_id:032x}"
        asyncio.run(pub.publish("items.created", {"id": "item-1"}))

    assert captured["routing_key"] == "items.created"
    assert json.loads(captured["body"]) == {"id": "item-1"}
    assert "traceparent" in captured["headers"], "publisher must inject traceparent"
    injected_trace_id = captured["headers"]["traceparent"].split("-")[1]
    assert injected_trace_id == parent_trace_id


def test_publisher_silent_when_not_connected(span_exporter):
    """publish() on a disconnected publisher must not raise — graceful degradation."""
    from services.gateway.events import EventPublisher

    pub = EventPublisher("amqp://localhost")
    # No connect() called → _exchange is None
    asyncio.run(pub.publish("items.created", {"id": "item-1"}))


# ---------------------------------------------------------------------------
# Worker: extract trace context and continue the parent trace
# ---------------------------------------------------------------------------


def _fake_message(headers: dict, body: dict, routing_key: str = "items.created"):
    msg = MagicMock()
    msg.headers = headers
    msg.routing_key = routing_key
    msg.body = json.dumps(body).encode()

    class _NoopProcess:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return None

    msg.process = lambda: _NoopProcess()
    return msg


def test_worker_joins_producer_trace(span_exporter):
    """A traceparent in the message headers must become the parent of the consume span."""
    import structlog

    from services.notifications_svc.worker import _handle_message

    span_exporter.clear()
    expected = "0123456789abcdef0123456789abcdef"
    msg = _fake_message(
        {"traceparent": f"00-{expected}-0123456789abcdef-01"},
        {"id": "item-1", "owner_id": "u1"},
    )

    asyncio.run(_handle_message(msg, structlog.get_logger("test")))

    consume_spans = [s for s in span_exporter.get_finished_spans() if s.name.startswith("consume")]
    assert consume_spans, "expected at least one consume span"
    for s in consume_spans:
        assert f"{s.context.trace_id:032x}" == expected


def test_worker_creates_nested_send_email_span(span_exporter):
    """The worker should create a child span for the simulated work."""
    import structlog

    from services.notifications_svc.worker import _handle_message

    span_exporter.clear()
    msg = _fake_message(
        {"traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"},
        {"id": "item-x", "owner_id": "u1"},
    )

    asyncio.run(_handle_message(msg, structlog.get_logger("test")))

    by_name = {s.name: s for s in span_exporter.get_finished_spans()}
    assert "send_email" in by_name
    assert "consume items.created" in by_name
    # Same trace
    assert (
        by_name["send_email"].context.trace_id == by_name["consume items.created"].context.trace_id
    )
    # send_email is a child of consume
    assert by_name["send_email"].parent.span_id == by_name["consume items.created"].context.span_id


def test_worker_handles_message_without_traceparent(span_exporter):
    """A message with no headers must still be processed (starts a new trace)."""
    import structlog

    from services.notifications_svc.worker import _handle_message

    span_exporter.clear()
    msg = _fake_message({}, {"id": "no-trace"})
    # Must not raise
    asyncio.run(_handle_message(msg, structlog.get_logger("test")))
    assert any(s.name.startswith("consume") for s in span_exporter.get_finished_spans())
