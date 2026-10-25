"""Catalogue of client-facing API errors.

Every payload built here is bilingual, generic and free of internal details: the client learns
what happened, the logs learn why. Nothing sensitive crosses this boundary.
"""

from __future__ import annotations

from typing import Final

UNAUTHORIZED_CODE: Final[str] = "unauthorized"
QUOTA_EXHAUSTED_CODE: Final[str] = "quota_exhausted"
PROVIDER_REJECTED_CODE: Final[str] = "provider_rejected"
PROVIDER_UNAVAILABLE_CODE: Final[str] = "provider_unavailable"
STREAMING_UNSUPPORTED_CODE: Final[str] = "streaming_unsupported"
INTERNAL_ERROR_CODE: Final[str] = "internal_error"


class ApiError(Exception):
    """An error whose payload is safe to return to the client in Spanish and English.

    Attributes:
        status_code: HTTP status returned to the caller.
        code: Stable machine-readable identifier used by the extension.
        es: Spanish message shown to the user.
        en: English message shown to the user.
        headers: Extra HTTP headers attached to the response.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        es: str,
        en: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(en)
        self.status_code = status_code
        self.code = code
        self.es = es
        self.en = en
        self.headers = headers or {}

    @property
    def detail(self) -> dict[str, str]:
        """Return the bilingual body sent as `detail` in the error response."""
        return {"code": self.code, "es": self.es, "en": self.en}


def unauthorized() -> ApiError:
    """Return the 401 raised when the caller has no valid Aquelarre API key."""
    return ApiError(
        status_code=401,
        code=UNAUTHORIZED_CODE,
        es="No autorizado: falta o no es válida la cabecera Authorization.",
        en="Unauthorized: the Authorization header is missing or invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def quota_exhausted() -> ApiError:
    """Return the 503 raised when no provider has quota left."""
    return ApiError(
        status_code=503,
        code=QUOTA_EXHAUSTED_CODE,
        es="Cuota agotada: ningún proveedor tiene cuota disponible en este momento.",
        en="Quota exhausted: no provider has quota available right now.",
    )


def provider_rejected() -> ApiError:
    """Return the 502 raised when a provider rejects our credentials."""
    return ApiError(
        status_code=502,
        code=PROVIDER_REJECTED_CODE,
        es="Proveedor no disponible: clave del proveedor inválida.",
        en="Provider unavailable: invalid provider key.",
    )


def provider_unavailable() -> ApiError:
    """Return the 500 raised when a provider fails for an unspecified reason."""
    return ApiError(
        status_code=500,
        code=PROVIDER_UNAVAILABLE_CODE,
        es="Proveedor no disponible: la petición no pudo completarse.",
        en="Provider unavailable: the request could not be completed.",
    )


def streaming_unsupported() -> ApiError:
    """Return the 400 raised when a client asks for streaming, which the MVP does not implement."""
    return ApiError(
        status_code=400,
        code=STREAMING_UNSUPPORTED_CODE,
        es="Streaming no soportado todavía: envía stream=false.",
        en="Streaming is not supported yet: send stream=false.",
    )
