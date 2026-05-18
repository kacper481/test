"""Structured logging with automatic OTel trace_id / span_id injection.

Every log line is emitted as a single-line JSON object including:
- timestamp, level, event, service.name
- trace_id, span_id (injected by opentelemetry-instrumentation-logging)
"""

from __future__ import annotations

import logging
import sys

import structlog
from opentelemetry import trace


def _inject_trace_context(_, __, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = f"{ctx.trace_id:032x}"
        event_dict["span_id"] = f"{ctx.span_id:016x}"
    return event_dict


def configure_logging(service_name: str, level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _inject_trace_context,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bind permanent context to every log record from this service
    structlog.contextvars.bind_contextvars(**{"service.name": service_name})


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
