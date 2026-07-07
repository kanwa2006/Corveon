"""Uniform error model and exception hierarchy (docs/API.md conventions).

Every error response is ``{error_code, message, details, trace_id}``. Handlers
are registered once in ``app.main.create_app`` so every router raises typed
``AppError`` subclasses instead of hand-rolling ``HTTPException`` payloads.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.logging import get_logger, trace_id_var

logger = get_logger(__name__)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] | None = None
    trace_id: str | None = None


class AppError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


def _respond(status_code: int, error_code: str, message: str, details: Any = None) -> JSONResponse:
    body = ErrorResponse(
        error_code=error_code,
        message=message,
        details=details,
        trace_id=trace_id_var.get(),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error", error_code=exc.error_code, message=exc.message, path=request.url.path
    )
    return _respond(exc.status_code, exc.error_code, exc.message, exc.details)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _respond(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Request validation failed.",
        {"errors": exc.errors()},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error", error=str(exc), path=request.url.path, exc_info=exc)
    return _respond(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred.",
    )
