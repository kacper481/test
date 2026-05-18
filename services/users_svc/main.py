from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.logging import configure_logging, get_logger
from common.opensearch import ensure_index, make_client
from common.settings import UsersSvcSettings
from common.telemetry import configure_telemetry

from .routes import router
from .store import INDEX, MAPPINGS


def create_app() -> FastAPI:
    settings = UsersSvcSettings()
    configure_logging(settings.service_name, settings.log_level)
    log = get_logger("users_svc.main")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.os_client = make_client(settings.opensearch_host)
        ensure_index(app.state.os_client, INDEX, MAPPINGS)
        log.info("service.started", service=settings.service_name, port=settings.port)
        yield
        log.info("service.stopped", service=settings.service_name)

    app = FastAPI(title="users-svc", lifespan=lifespan)
    app.include_router(router)
    configure_telemetry(app, settings.service_name, settings.otel_exporter_otlp_endpoint)
    return app


app = create_app()
