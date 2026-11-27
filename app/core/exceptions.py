"""Typed application errors and the handlers that turn every error into `ApiResponse`.

Services raise `AppError` subclasses with a `Msg` key. Never raise `HTTPException` in features.
`error_response(...)` builds an envelope for use inside middleware (which cannot rely on handlers).
"""

import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from app.core.constants import ErrorCode, Header
from app.core.i18n import t
from app.core.messages import Msg
from app.shared.schemas import ApiResponse

log = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = ErrorCode.INTERNAL
    default_msg = Msg.INTERNAL_ERROR

    def __init__(
        self,
        msg: Msg | None = None,
        *,
        details: object = None,
        headers: dict[str, str] | None = None,
        **params: object,
    ):
        self.msg = msg or self.default_msg
        self.params = params
        self.details = details
        self.headers = headers or {}
        super().__init__(str(self.msg))


class NotFoundError(AppError):
    status_code, code, default_msg = 404, ErrorCode.NOT_FOUND, Msg.NOT_FOUND


class UnauthorizedError(AppError):
    status_code, code, default_msg = 401, ErrorCode.UNAUTHORIZED, Msg.UNAUTHORIZED


class ForbiddenError(AppError):
    status_code, code, default_msg = 403, ErrorCode.FORBIDDEN, Msg.FORBIDDEN


class ConflictError(AppError):
    status_code, code, default_msg = 409, ErrorCode.CONFLICT, Msg.CONFLICT


class BadInputError(AppError):
    status_code, code, default_msg = 422, ErrorCode.VALIDATION, Msg.VALIDATION_ERROR


class RateLimitedError(AppError):
    status_code, code, default_msg = 429, ErrorCode.RATE_LIMITED, Msg.RATE_LIMITED

    def __init__(self, retry_after: int, **params: Any):
        super().__init__(headers={Header.RETRY_AFTER: str(retry_after)}, **params)
        self.retry_after = retry_after


class PayloadTooLargeError(AppError):
    status_code, code, default_msg = 413, ErrorCode.PAYLOAD_TOO_LARGE, Msg.PAYLOAD_TOO_LARGE


class ServiceUnavailableError(AppError):
    status_code, code, default_msg = 503, ErrorCode.SERVICE_UNAVAILABLE, Msg.NOT_READY


class PreconditionFailedError(AppError):
    status_code, code, default_msg = 412, ErrorCode.PRECONDITION_FAILED, Msg.PRECONDITION_FAILED


class PreconditionRequiredError(AppError):
    status_code, code, default_msg = 428, ErrorCode.PRECONDITION_REQUIRED, Msg.PRECONDITION_REQUIRED


def error_response(
    status: int,
    code: ErrorCode,
    message: str,
    details: object = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an error envelope response (usable from middleware, no exception handling needed)."""
    body = ApiResponse[object](success=False, code=code, message=message, data=details)
    return JSONResponse(
        body.model_dump(mode="json", by_alias=True), status_code=status, headers=headers
    )


def _error(
    status: int,
    code: ErrorCode,
    message: str,
    details: object = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return error_response(status, code, message, details, headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(
            exc.status_code,
            exc.code,
            t(exc.msg, **cast("dict[str, Any]", exc.params)),
            exc.details,
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(map(str, e["loc"][1:])), "issue": e["msg"]} for e in exc.errors()
        ]
        return _error(422, ErrorCode.VALIDATION, t(Msg.VALIDATION_ERROR), details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        headers = dict(exc.headers or {})
        if exc.status_code == 405:
            methods: set[str] = set()
            for route in app.routes:
                match, _ = route.matches(request.scope)
                if match == Match.PARTIAL:
                    methods.update(getattr(route, "methods", None) or ())
            if methods:
                headers["Allow"] = ", ".join(sorted(methods))
        missing = exc.status_code == 404
        code = ErrorCode.NOT_FOUND if missing else ErrorCode.INTERNAL
        return _error(
            exc.status_code,
            code,
            t(Msg.NOT_FOUND if missing else Msg.INTERNAL_ERROR),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return _error(500, ErrorCode.INTERNAL, t(Msg.INTERNAL_ERROR))
