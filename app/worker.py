"""Standalone worker process: `python -m app.worker` (or `make worker`)."""

import asyncio
import logging
import signal

from app.core.cache import close_cache
from app.core.database import connect_db, disconnect_db
from app.core.discovery import feature_modules
from app.core.jobs import Worker, get_store
from app.core.logging import configure_logging

log = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    feature_modules("jobs")  # registers every @job_handler
    await connect_db()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await Worker(get_store()).run(stop)
    finally:
        await close_cache()
        await disconnect_db()


if __name__ == "__main__":
    asyncio.run(main())
