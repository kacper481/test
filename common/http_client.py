"""Shared async HTTP client for service-to-service calls.

`HTTPXClientInstrumentor` (configured in `common.telemetry`) automatically:
- creates a child span for every outgoing request
- injects W3C `traceparent` + `baggage` headers so the downstream service
  joins the same trace
"""

from __future__ import annotations

import httpx


def make_client(timeout: float = 5.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
