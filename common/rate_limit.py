"""Per-IP rate limiting for the gateway, opt-in via env.

Set `RATE_LIMIT_PER_MINUTE=N` (positive integer) to enforce. Unset / 0 disables.

`install()` reads the env at call time and builds a fresh limiter, so there is
no leaky module-level state across app instances (important for tests).

This uses slowapi (a Starlette/FastAPI port of Flask-Limiter) with an
in-memory store. For multi-replica production deployments, point the limiter
at a shared Redis store via `storage_uri` — see the slowapi docs.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def _limit_str() -> str | None:
    raw = os.getenv("RATE_LIMIT_PER_MINUTE")
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return f"{n}/minute" if n > 0 else None


def install(app: FastAPI) -> None:
    """Attach a rate limiter to the app. No-op if RATE_LIMIT_PER_MINUTE unset."""
    limit = _limit_str()
    if not limit:
        return

    limiter = Limiter(key_func=get_remote_address, default_limits=[limit], enabled=True)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
