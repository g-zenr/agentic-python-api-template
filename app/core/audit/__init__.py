"""Audit subsystem: append-only "who changed what" logging.

Services call `audit.record(...)`. The sink defaults to the database repository; tests swap it.
"""

from app.core.audit.recorder import record, set_sink

__all__ = ["record", "set_sink"]
