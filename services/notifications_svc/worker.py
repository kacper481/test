"""Async worker — consumes `items.created` events from RabbitMQ.

This service has no HTTP API. It exists to demonstrate:
1. Cross-process trace context propagation through a message queue.
2. How `propagate.extract()` rebuilds the trace from headers a producer set
   with `propagate.inject()` — the trace continues seamlessly.

Run with:  python -m services.notifications_svc.worker
"""
from __future__ import annotations

import asyncio
import json

import aio_pika
from opentelemetry import propagate, trace

from common import metrics as m
from common.logging import configure_logging, get_logger
from common.settings import NotificationsSvcSettings
from common.telemetry import configure_telemetry


_tracer = trace.get_tracer(__name__)


async def _handle_message(message: aio_pika.abc.AbstractIncomingMessage, log) -> None:
    async with message.process():
        headers = {k: v for k, v in (message.headers or {}).items() if isinstance(v, str)}
        # Re-attach the trace context the producer injected into the headers.
        ctx = propagate.extract(headers)

        with _tracer.start_as_current_span(
            f"consume {message.routing_key}",
            context=ctx,
            kind=trace.SpanKind.CONSUMER,
        ) as span:
            span.set_attribute("messaging.system", "rabbitmq")
            span.set_attribute("messaging.operation", "process")
            span.set_attribute("messaging.rabbitmq.routing_key", message.routing_key or "")

            payload = json.loads(message.body)
            log.info("event.received", routing_key=message.routing_key, item_id=payload.get("id"))

            # Simulate "send notification" work — this span shows up inline
            # in Jaeger as a child of the producer's trace.
            with _tracer.start_as_current_span("send_email") as work_span:
                work_span.set_attribute("notification.channel", "email")
                work_span.set_attribute("item.id", payload.get("id", ""))
                await asyncio.sleep(0.05)

            m.notifications_sent.add(1, {"channel": "email"})
            log.info("notification.sent", item_id=payload.get("id"))


async def main() -> None:
    settings = NotificationsSvcSettings()
    configure_logging(settings.service_name, settings.log_level)
    configure_telemetry(None, settings.service_name, settings.otel_exporter_otlp_endpoint)

    log = get_logger("notifications_svc.worker")
    log.info("worker.connecting", amqp_url=settings.amqp_url)

    connection = await aio_pika.connect_robust(settings.amqp_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        "events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue("notifications", durable=True)
    await queue.bind(exchange, routing_key="items.created")

    log.info("worker.started", queue="notifications", binding="items.created")

    async with queue.iterator() as it:
        async for message in it:
            try:
                await _handle_message(message, log)
            except Exception as exc:
                log.exception("worker.handler_failed", error=str(exc))


if __name__ == "__main__":
    asyncio.run(main())
