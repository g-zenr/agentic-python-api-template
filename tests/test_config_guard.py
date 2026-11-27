"""Production config guard tests: unsafe prod configs are rejected, dev is never blocked."""

import pytest
from pydantic import ValidationError

from app.core.config import McpClientConfig, Settings

_VALID = dict(
    env="prod",
    jwt_secret="x" * 40,
    cors_origins=["https://app.example.com"],
    allowed_hosts=["example.com"],
    database_url="postgresql://x/y",
    cache_backend="redis",
    worker_embedded=False,
    log_format="json",
    email_backend="smtp",
    app_base_url="https://example.com",
    mcp_clients=[McpClientConfig(name="c", key_sha256="h")],
    metrics_token="tok",
    audit_fail_closed=True,
    authz_fail_closed=True,
    require_email_verification=True,
    email_from="no-reply@example.org",
)


def test_valid_prod_config_passes():
    Settings(**_VALID)


def test_dev_is_never_blocked():
    Settings(env="dev")  # dev with defaults must not raise


@pytest.mark.parametrize(
    "override",
    [
        {"jwt_secret": "short"},
        {"cors_origins": ["*"]},
        {"allowed_hosts": ["*"]},
        {"database_url": ""},
        {"cache_backend": "memory"},
        {"worker_embedded": True},
        {"log_format": "text"},
        {"email_backend": "console"},
        {"app_base_url": "http://x"},
        {"mcp_clients": []},
        {"metrics_token": None},
        {"audit_fail_closed": False},
        {"authz_fail_closed": False},
        {"require_email_verification": False},
        {"email_from": "no-reply@example.com"},
    ],
)
def test_each_unsafe_setting_reported(override):
    with pytest.raises(ValidationError):
        Settings(**{**_VALID, **override})


def test_guard_reports_all_problems_at_once():
    with pytest.raises(ValidationError) as exc:
        Settings(**{**_VALID, "jwt_secret": "short", "cors_origins": ["*"]})
    assert "Unsafe production configuration" in str(exc.value)
