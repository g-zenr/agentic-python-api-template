"""Activity subsystem: high-volume, best-effort request logging.

`activity.record_request(...)` is called by middleware; a background task batches writes.
"""

from app.core.activity.buffer import ActivityBuffer, activity

__all__ = ["ActivityBuffer", "activity"]
