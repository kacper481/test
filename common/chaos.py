"""Chaos injection — env-var-toggled latency and error injection for exercises.

These are deliberate, opt-in misbehaviors so learners can practice debugging
with OpenTelemetry. None of them fire unless the corresponding env var is set.

Env vars
--------
CHAOS_ITEMS_SEARCH_MS=200          # add N ms of latency to items search
CHAOS_USERS_GET_ERROR_RATE=0.2     # 20% chance users.get returns 500
CHAOS_OS_INDEX_SLOW_MS=150         # add latency to every OpenSearch index op
CHAOS_GATEWAY_VALIDATE_MS=80       # add latency to gateway's owner-validation hop
"""

from __future__ import annotations

import os
import random
import time

from fastapi import HTTPException
from opentelemetry import trace

_tracer = trace.get_tracer(__name__)


def maybe_delay(env_var: str, span_name: str = "chaos.delay") -> None:
    """If env_var is set to N (ms), sleep for N ms and record a span attribute."""
    raw = os.getenv(env_var)
    if not raw:
        return
    try:
        ms = int(raw)
    except ValueError:
        return
    if ms <= 0:
        return

    span = trace.get_current_span()
    span.set_attribute("chaos.delay_ms", ms)
    span.set_attribute("chaos.source", env_var)
    time.sleep(ms / 1000)


def maybe_fail(env_var: str, status: int = 500, detail: str = "chaos!") -> None:
    """If env_var is set to a rate (0..1), randomly raise HTTPException."""
    raw = os.getenv(env_var)
    if not raw:
        return
    try:
        rate = float(raw)
    except ValueError:
        return
    if rate <= 0:
        return

    if random.random() < rate:
        span = trace.get_current_span()
        span.set_attribute("chaos.failure", True)
        span.set_attribute("chaos.source", env_var)
        raise HTTPException(status_code=status, detail=detail)
