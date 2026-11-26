"""Single shared Prisma client plus connect/disconnect hooks used by the app lifespan."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import settings
from prisma import Prisma


def build_database_url() -> str:
    """Append connection_limit and pool_timeout to the URL unless already present."""
    url = settings.database_url
    if not url:
        return url
    parts = urlsplit(url)
    existing = dict(parse_qsl(parts.query))
    existing.setdefault("connection_limit", str(settings.db_connection_limit))
    existing.setdefault("pool_timeout", str(settings.db_pool_timeout_seconds))
    return urlunsplit(parts._replace(query=urlencode(existing)))


db = Prisma(auto_register=True, datasource={"url": build_database_url()})


async def connect_db() -> None:
    if not db.is_connected():
        await db.connect()


async def disconnect_db() -> None:
    if db.is_connected():
        await db.disconnect()
