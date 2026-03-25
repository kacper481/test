from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from opensearchpy import NotFoundError
from pydantic import BaseModel

load_dotenv()

import app.opensearch as os_service  # noqa: E402  (after load_dotenv)


@asynccontextmanager
async def lifespan(application: FastAPI):
    os_service.ensure_index()
    yield


app = FastAPI(title="Items API", lifespan=lifespan)

# OpenTelemetry is configured after the app object exists
from app.telemetry import configure_telemetry  # noqa: E402

configure_telemetry(app)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ItemCreate(BaseModel):
    title: str
    description: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
def health():
    """Service liveness + OpenSearch connectivity check."""
    try:
        info = os_service.client.info()
        return {
            "status": "ok",
            "opensearch": {
                "version": info["version"]["number"],
                "cluster": info["cluster_name"],
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenSearch unavailable: {exc}")


@app.post("/items", status_code=201, tags=["items"])
def create_item(payload: ItemCreate):
    """Store a new item in OpenSearch and return it with its generated ID."""
    return os_service.create_item(payload.title, payload.description)


@app.get("/items/{item_id}", tags=["items"])
def get_item(item_id: str):
    """Retrieve a single item by its ID."""
    try:
        return os_service.get_item(item_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Item not found")


@app.get("/items", tags=["items"])
def list_items(q: Optional[str] = None):
    """List all items, or full-text search with an optional ?q= parameter."""
    return os_service.search_items(q)
