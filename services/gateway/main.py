from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.http_client import make_client
from common.logging import configure_logging, get_logger
from common.settings import GatewaySettings
from common.telemetry import configure_telemetry
from .events import EventPublisher
from .routes import router


def create_app() -> FastAPI:
    settings = GatewaySettings()
    configure_logging(settings.service_name, settings.log_level)
    log = get_logger("gateway.main")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = make_client()
        app.state.items_url = settings.items_svc_url
        app.state.users_url = settings.users_svc_url

        app.state.publisher = EventPublisher(settings.amqp_url)
        try:
            await app.state.publisher.connect()
            log.info("publisher.connected", amqp_url=settings.amqp_url)
        except Exception as exc:
            log.warning("publisher.connect_failed", error=str(exc))

        log.info(
            "service.started",
            service=settings.service_name,
            port=settings.port,
            items_url=settings.items_svc_url,
            users_url=settings.users_svc_url,
        )
        yield
        await app.state.http.aclose()
        try:
            await app.state.publisher.close()
        except Exception:
            pass
        log.info("service.stopped", service=settings.service_name)

    app = FastAPI(title="gateway", lifespan=lifespan)
    app.include_router(router)
    configure_telemetry(app, settings.service_name, settings.otel_exporter_otlp_endpoint)
    return app


app = create_app()
