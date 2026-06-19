"""API key authentication for the gateway.

Opt-in: only enforces when the `GATEWAY_API_KEY` env var is set. With it unset
(the default for the learning environment), endpoints remain wide open.

Usage:
    from common.auth import require_api_key
    router = APIRouter(dependencies=[Depends(require_api_key)])

For real production, replace this with OAuth/JWT and store keys in a secret
manager — never in env vars or .env files committed to source control.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_HEADER_NAME = "X-API-Key"
_api_key_header = APIKeyHeader(name=_HEADER_NAME, auto_error=False)


def require_api_key(provided: str | None = Security(_api_key_header)) -> None:
    """FastAPI dependency. Reads GATEWAY_API_KEY fresh on every request.

    - unset      -> auth disabled (learning mode)
    - set        -> require a matching X-API-Key header
    """
    expected = os.getenv("GATEWAY_API_KEY")
    if not expected:
        return  # auth disabled

    if not provided:
        raise HTTPException(
            status_code=401,
            detail=f"Missing {_HEADER_NAME} header",
            headers={"WWW-Authenticate": _HEADER_NAME},
        )
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")
