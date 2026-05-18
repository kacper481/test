from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from opentelemetry import baggage, context, trace
from pydantic import BaseModel, EmailStr, Field

from common import chaos
from common.logging import get_logger

log = get_logger("gateway.routes")
router = APIRouter()
_tracer = trace.get_tracer(__name__)


class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    owner_id: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attach_request_baggage(request: Request) -> object:
    """Attach a request.id to OTel baggage so downstreams can see it on every span."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    ctx = baggage.set_baggage("request.id", request_id)
    token = context.attach(ctx)
    span = trace.get_current_span()
    span.set_attribute("request.id", request_id)
    return token


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def health(request: Request):
    client = request.app.state.http
    items_url = request.app.state.items_url
    users_url = request.app.state.users_url

    items_resp, users_resp = await asyncio.gather(
        client.get(f"{items_url}/health"),
        client.get(f"{users_url}/health"),
        return_exceptions=True,
    )

    def _summarize(r):
        if isinstance(r, Exception):
            return {"status": "down", "error": str(r)}
        return {"status": "up" if r.status_code == 200 else "degraded", "code": r.status_code}

    return {
        "status": "ok",
        "items_svc": _summarize(items_resp),
        "users_svc": _summarize(users_resp),
    }


@router.post("/api/users", status_code=201)
async def create_user(payload: UserCreate, request: Request):
    token = _attach_request_baggage(request)
    try:
        resp = await request.app.state.http.post(
            f"{request.app.state.users_url}/users", json=payload.model_dump()
        )
        resp.raise_for_status()
        user = resp.json()
        log.info("gateway.user.created", user_id=user["id"])
        return user
    finally:
        context.detach(token)


@router.get("/api/users/{user_id}")
async def get_user(user_id: str, request: Request):
    token = _attach_request_baggage(request)
    try:
        resp = await request.app.state.http.get(
            f"{request.app.state.users_url}/users/{user_id}"
        )
        if resp.status_code == 404:
            raise HTTPException(404, "User not found")
        resp.raise_for_status()
        return resp.json()
    finally:
        context.detach(token)


@router.post("/api/items", status_code=201)
async def create_item(payload: ItemCreate, request: Request):
    """Validate the owner exists, then create the item — two downstream hops."""
    token = _attach_request_baggage(request)
    try:
        http = request.app.state.http

        with _tracer.start_as_current_span("gateway.validate_owner") as span:
            span.set_attribute("item.owner_id", payload.owner_id)
            chaos.maybe_delay("CHAOS_GATEWAY_VALIDATE_MS")
            owner_resp = await http.get(
                f"{request.app.state.users_url}/users/{payload.owner_id}"
            )
            if owner_resp.status_code == 404:
                raise HTTPException(400, f"Unknown owner_id: {payload.owner_id}")
            owner_resp.raise_for_status()

        create_resp = await http.post(
            f"{request.app.state.items_url}/items", json=payload.model_dump()
        )
        create_resp.raise_for_status()
        item = create_resp.json()

        # Fire-and-forget event; trace context is propagated in message headers
        try:
            await request.app.state.publisher.publish("items.created", item)
        except Exception as exc:
            log.warning("publish.failed", error=str(exc))

        log.info("gateway.item.created", item_id=item["id"], owner_id=payload.owner_id)
        return item
    finally:
        context.detach(token)


@router.get("/api/items/{item_id}")
async def get_item(item_id: str, request: Request):
    """Fetch item + owner concurrently."""
    token = _attach_request_baggage(request)
    try:
        http = request.app.state.http

        async def _fetch_item():
            r = await http.get(f"{request.app.state.items_url}/items/{item_id}")
            if r.status_code == 404:
                raise HTTPException(404, "Item not found")
            r.raise_for_status()
            return r.json()

        async def _fetch_owner(owner_id: str):
            r = await http.get(f"{request.app.state.users_url}/users/{owner_id}")
            return r.json() if r.status_code == 200 else None

        item = await _fetch_item()
        owner = await _fetch_owner(item["owner_id"])
        return {**item, "owner": owner}
    finally:
        context.detach(token)


@router.get("/api/items")
async def search_items(
    request: Request,
    q: Optional[str] = None,
    owner_id: Optional[str] = None,
):
    """Search items, then hydrate owners in a single batch call."""
    token = _attach_request_baggage(request)
    try:
        http = request.app.state.http
        params = {k: v for k, v in {"q": q, "owner_id": owner_id}.items() if v}

        search_resp = await http.get(
            f"{request.app.state.items_url}/items", params=params
        )
        search_resp.raise_for_status()
        result = search_resp.json()

        owner_ids = list({hit["owner_id"] for hit in result["hits"]})
        if owner_ids:
            with _tracer.start_as_current_span("gateway.hydrate_owners") as span:
                span.set_attribute("hydrate.owner_count", len(owner_ids))
                mget_resp = await http.post(
                    f"{request.app.state.users_url}/users/_mget",
                    json={"ids": owner_ids},
                )
                mget_resp.raise_for_status()
                owners_by_id = {u["id"]: u for u in mget_resp.json()["users"]}
        else:
            owners_by_id = {}

        for hit in result["hits"]:
            hit["owner"] = owners_by_id.get(hit["owner_id"])

        log.info("gateway.items.searched", query=q, count=len(result["hits"]))
        return result
    finally:
        context.detach(token)
