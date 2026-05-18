from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from opensearchpy import NotFoundError
from pydantic import BaseModel, EmailStr, Field

from common.logging import get_logger

from . import store

log = get_logger("users_svc.routes")
router = APIRouter()


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None


class MgetRequest(BaseModel):
    ids: list[str]


@router.get("/health")
def health(request: Request):
    try:
        info = request.app.state.os_client.info()
        return {"status": "ok", "opensearch_version": info["version"]["number"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenSearch unavailable: {exc}") from exc


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, request: Request):
    user = store.create_user(request.app.state.os_client, payload.name, payload.email)
    log.info("user.created", user_id=user["id"])
    return user


@router.get("/users/{user_id}")
def get_user(user_id: str, request: Request):
    try:
        return store.get_user(request.app.state.os_client, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None


@router.post("/users/_mget")
def mget(payload: MgetRequest, request: Request):
    users = store.mget_users(request.app.state.os_client, payload.ids)
    return {"users": users}
