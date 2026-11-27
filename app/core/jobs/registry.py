"""Job handler registry: map a JobType to its async handler and policy.

Handlers MUST be idempotent (delivery is at-least-once) and return a SMALL JSON-safe dict or None.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.core.constants import JobPolicy, JobType
from app.core.jobs.types import PermanentError
from app.core.messages import Msg


@dataclass(frozen=True)
class Handler:
    job_type: JobType
    fn: Callable[..., Awaitable[dict[str, Any] | None]]
    payload_model: type[BaseModel] | None
    timeout: int
    max_attempts: int
    schedule_every: int | None


_handlers: dict[JobType, Handler] = {}


def job_handler(
    type_: JobType,
    *,
    payload: type[BaseModel] | None = None,
    timeout: int = JobPolicy.DEFAULT_TIMEOUT,
    max_attempts: int = JobPolicy.DEFAULT_MAX_ATTEMPTS,
    schedule_every: int | None = None,
) -> Callable[
    [Callable[..., Awaitable[dict[str, Any] | None]]],
    Callable[..., Awaitable[dict[str, Any] | None]],
]:
    """Register an async handler: `fn(ctx)`, or `fn(ctx, payload)` when `payload` is set."""

    def wrap(
        fn: Callable[..., Awaitable[dict[str, Any] | None]],
    ) -> Callable[..., Awaitable[dict[str, Any] | None]]:
        if type_ in _handlers:
            raise RuntimeError(f"job handler already registered: {type_}")
        _handlers[type_] = Handler(
            job_type=type_,
            fn=fn,
            payload_model=payload,
            timeout=timeout,
            max_attempts=max_attempts,
            schedule_every=schedule_every,
        )
        return fn

    return wrap


def get_handler(type_: str | JobType) -> Handler:
    key = JobType(type_) if not isinstance(type_, JobType) else type_
    handler = _handlers.get(key)
    if handler is None:
        raise PermanentError(Msg.JOB_UNKNOWN_TYPE)
    return handler


def handlers() -> dict[JobType, Handler]:
    return dict(_handlers)
