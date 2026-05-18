"""RabbitMQ event publisher for the gateway.

Demonstrates manual trace context propagation across an async boundary:
- We call `propagate.inject(headers)` BEFORE publishing, which writes the
  current span's `traceparent` (and any baggage) into the message headers.
- The consumer side (notifications-svc) calls `propagate.extract(headers)`
  to continue the same trace.

The `AioPikaInstrumentor` auto-instruments aio-pika as well, but doing it
manually here makes the propagation mechanism visible.
"""
from __future__ import annotations

import json
from typing import Any

import aio_pika
from opentelemetry import propagate, trace

_tracer = trace.get_tracer(__name__)


class EventPublisher:
    def __init__(self, amqp_url: str):
        self._amqp_url = amqp_url
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            "events", aio_pika.ExchangeType.TOPIC, durable=True
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if self._exchange is None:
            return  # publisher not connected — skip silently

        with _tracer.start_as_current_span(f"publish {routing_key}") as span:
            span.set_attribute("messaging.system", "rabbitmq")
            span.set_attribute("messaging.destination", "events")
            span.set_attribute("messaging.rabbitmq.routing_key", routing_key)

            # Inject the current trace context into the message headers so the
            # consumer can continue the same trace.
            headers: dict[str, str] = {}
            propagate.inject(headers)

            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                headers=headers,
                content_type="application/json",
            )
            await self._exchange.publish(message, routing_key=routing_key)
