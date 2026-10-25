"""FastAPI exception handlers turning domain failures into bilingual HTTP responses."""

from __future__ import annotations

import logging
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import ApiError, provider_unavailable
from app.core.security import sanitize_for_logs

logger: Final[logging.Logger] = logging.getLogger("app.api.errors")

INVALID_REQUEST_CODE: Final[str] = "invalid_request"
INVALID_REQUEST_ES: Final[str] = (
    "Cuerpo de la petición no válido: revisa messages, model y temperature."
)
INVALID_REQUEST_EN: Final[str] = "Invalid request body: check messages, model and temperature."


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler the application relies on.

    Args:
        app: Application instance being assembled.
    """
    app.add_exception_handler(ApiError, _api_error_response)
    app.add_exception_handler(RequestValidationError, _validation_error_response)
    app.add_exception_handler(Exception, _unexpected_error_response)


def _api_error_response(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


def _validation_error_response(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = {"code": INVALID_REQUEST_CODE, "es": INVALID_REQUEST_ES, "en": INVALID_REQUEST_EN}
    return JSONResponse(status_code=422, content={"detail": detail})


def _unexpected_error_response(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled error on %s: %s",
        request.url.path,
        sanitize_for_logs(str(exc)),
        exc_info=True,
    )
    error = provider_unavailable()
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
