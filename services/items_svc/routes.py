from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from opensearchpy import NotFoundError
from pydantic import BaseModel, Field

from common.logging import get_logger

from . import store

log = get_logger("items_svc.routes")
router = APIRouter()


class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    owner_id: str = Field(min_length=1)


@router.get("/health")
def health(request: Request):
    try:
        info = request.app.state.os_client.info()
        return {"status": "ok", "opensearch_version": info["version"]["number"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenSearch unavailable: {exc}") from exc


@router.post("/items", status_code=201)
def create_item(payload: ItemCreate, request: Request):
    item = store.create_item(
        request.app.state.os_client,
        payload.title,
        payload.description,
        payload.owner_id,
    )
    log.info("item.created", item_id=item["id"], owner_id=payload.owner_id)
    return item


@router.get("/items/{item_id}")
def get_item(item_id: str, request: Request):
    try:
        return store.get_item(request.app.state.os_client, item_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Item not found") from None


@router.get("/items")
def search_items(request: Request, q: str | None = None, owner_id: str | None = None):
    result = store.search_items(request.app.state.os_client, q, owner_id)
    log.info("items.searched", query=q, owner_id=owner_id, count=len(result["hits"]))
    return result
