"""Environment-driven settings. The ONLY module that reads environment variables.

Deployment decisions (secrets, URLs, toggles) live here and in `.env.example`.
Static, non-environment literals belong in `constants.py`.
The app version is NOT defined here: it is read from `pyproject.toml` (single source of truth).
A production guard rejects unsafe configurations at startup (see `_prod_problems`).
"""

import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import Defaults

_PACKAGE = "agentic-api"


def _read_version() -> str:
    """Installed metadata first; else parse pyproject.toml (uv without install)."""
    try:
        return version(_PACKAGE)
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        return tomllib.loads(pyproject.read_text("utf-8"))["project"]["version"]


class McpClientConfig(BaseModel):
    name: str
    key_sha256: str
    tools: list[str] = ["*"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Agentic API"
    app_version: str = _read_version()
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]
    allowed_hosts: list[str] = ["*"]

    database_url: str = ""
    direct_database_url: str = ""
    jwt_secret: SecretStr = SecretStr(Defaults.JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    require_email_verification: bool = False

    max_body_bytes: int = 1_048_576
    rate_limit_enabled: bool = True
    rate_limit_global_per_minute: int = 300

    log_format: Literal["text", "json"] = "text"
    metrics_enabled: bool = True
    metrics_token: SecretStr | None = None
    worker_metrics_port: int = 9100
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = 0.0
    otel_enabled: bool = False
    otel_service_name: str = "agentic-api"
    otel_exporter_otlp_endpoint: str | None = None

    db_connection_limit: int = 10
    db_pool_timeout_seconds: int = 10
    db_tx_timeout_ms: int = 10_000
    health_check_timeout_seconds: float = 2.0

    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "no-reply@example.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    app_base_url: str = "http://localhost:3000"
    verification_token_ttl_hours: int = 24
    reset_token_ttl_minutes: int = 30
    account_erase_delay_days: int = 7
    audit_pii_retention_days: int = 90
    idempotency_ttl_hours: int = 24

    default_locale: str = "en"
    supported_locales: list[str] = ["en", "fil"]

    mcp_enabled: bool = True
    mcp_mount_path: str = "/mcp"
    mcp_clients: list[McpClientConfig] = []

    cache_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    cache_prefix: str = "agentic"
    cache_memory_max_items: int = 10_000

    worker_embedded: bool = True
    worker_concurrency: int = 4
    worker_poll_seconds: float = 1.0
    job_stale_seconds: int = 120
    job_retention_days: int = 14
    job_poll_hint_seconds: int = 2

    activity_enabled: bool = True
    activity_batch_size: int = 100
    activity_flush_seconds: float = 2.0
    activity_queue_max: int = 10_000
    activity_retention_days: int = 30
    audit_retention_days: int = 365
    audit_fail_closed: bool = False
    trust_proxy_headers: bool = False

    @model_validator(mode="after")
    def _check_prod(self) -> "Settings":
        if self.env == "prod":
            problems = _prod_problems(self)
            if problems:
                raise ValueError("Unsafe production configuration:\n- " + "\n- ".join(problems))
        return self


def _prod_problems(s: "Settings") -> list[str]:
    problems: list[str] = []
    secret = s.jwt_secret.get_secret_value()
    if not secret or secret == Defaults.JWT_SECRET or len(secret) < 32:
        problems.append("JWT_SECRET must be a strong secret of at least 32 characters")
    if s.cors_origins == ["*"]:
        problems.append("CORS_ORIGINS must not be '*' in production")
    if s.allowed_hosts == ["*"]:
        problems.append("ALLOWED_HOSTS must not be '*' in production")
    if not s.database_url:
        problems.append("DATABASE_URL is required")
    if s.cache_backend != "redis":
        problems.append("CACHE_BACKEND must be 'redis' in production")
    if s.worker_embedded:
        problems.append("WORKER_EMBEDDED must be false in production (run a separate worker)")
    if s.log_format != "json":
        problems.append("LOG_FORMAT must be 'json' in production")
    if s.email_backend == "console":
        problems.append("EMAIL_BACKEND must not be 'console' in production")
    if not s.app_base_url.startswith("https://"):
        problems.append("APP_BASE_URL must use https in production")
    if s.mcp_enabled and not s.mcp_clients:
        problems.append("MCP_ENABLED requires at least one MCP_CLIENTS entry in production")
    if s.metrics_enabled and s.metrics_token is None:
        problems.append("METRICS_ENABLED requires METRICS_TOKEN in production")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
