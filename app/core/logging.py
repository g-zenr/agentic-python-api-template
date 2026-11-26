"""Logging setup: level from settings, request id injected via a filter.

Call `configure_logging()` once at startup (done in `create_app`). The filter reads the
per-request request id from a ContextVar so every log line can be correlated with a request.
"""

import logging

from app.core.config import settings
from app.core.context import request_id_var

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"


class _RequestIdFilter(logging.Filter):
    """Attach the current request id (or `-`) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    """Configure root logging with the request-id filter installed."""
    logging.basicConfig(level=settings.log_level.upper(), format=_LOG_FORMAT)
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(_RequestIdFilter())
