"""Per-request/per-job context: ContextVars (request id, locale) and a mutable RequestContext.

A plain ContextVar set inside a dependency is NOT visible to middleware after `call_next`; the
mutable `RequestContext` object is. Dependencies mutate it; middleware reads it afterward.
"""

from contextvars import ContextVar
from dataclasses import dataclass

from app.core.config import settings
from app.core.constants import ActorType

locale_var: ContextVar[str] = ContextVar("locale", default=settings.default_locale)
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


@dataclass
class RequestContext:
    """Mutable per-request/per-job state. Dependencies mutate it; middleware reads it afterward."""

    request_id: str = "-"
    ip: str | None = None
    user_agent: str | None = None
    user_id: str | None = None
    actor_type: ActorType = ActorType.ANONYMOUS
    job_id: str | None = None


request_ctx: ContextVar[RequestContext | None] = ContextVar("request_ctx", default=None)
mcp_client_var: ContextVar[str | None] = ContextVar("mcp_client", default=None)


def current() -> RequestContext:
    ctx = request_ctx.get()
    if ctx is None:
        ctx = RequestContext()
        request_ctx.set(ctx)
    return ctx


def bind_user(user_id: str) -> None:
    ctx = current()
    ctx.user_id, ctx.actor_type = user_id, ActorType.USER
