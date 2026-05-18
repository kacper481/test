from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common settings inherited by every service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "unknown-service"
    port: int = 8000
    log_level: str = "INFO"

    opensearch_host: str = "http://localhost:9200"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"


class GatewaySettings(BaseServiceSettings):
    service_name: str = "gateway"
    port: int = 8000
    items_svc_url: str = "http://localhost:8001"
    users_svc_url: str = "http://localhost:8002"


class ItemsSvcSettings(BaseServiceSettings):
    service_name: str = "items-svc"
    port: int = 8001


class UsersSvcSettings(BaseServiceSettings):
    service_name: str = "users-svc"
    port: int = 8002
