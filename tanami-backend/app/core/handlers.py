"""Exception mapping to the error envelope in ``design.md`` 10.1.

Every failure leaves the process in exactly this shape, so the app only has to
branch on ``error.code``:

    {"error": {"code", "message", "details", "request_id"}}

``message`` is always Indonesian and safe to display (TQA 5.1).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.errors import STATUS_TO_CODE, AppError
from app.core.logging import get_logger

logger = get_logger("errors")

_DEFAULT_MESSAGES: dict[str, str] = {
    "validation_error": "Data yang dikirim tidak valid.",
    "unauthorized": "Sesi Anda tidak valid atau sudah berakhir.",
    "forbidden": "Anda tidak memiliki akses ke data ini.",
    "not_found": "Data tidak ditemukan.",
    "conflict": "Data sudah ada.",
    "payload_too_large": "Foto terlalu besar. Kompres ulang lalu coba lagi.",
    "unsupported_media_type": "Tipe berkas tidak didukung. Gunakan JPEG atau PNG.",
    "invalid_image": "Gambar tidak dapat diproses. Coba foto ulang.",
    "rate_limited": "Terlalu sering. Tunggu sebentar lalu coba lagi.",
    "internal_error": "Terjadi kesalahan pada server.",
    "service_unavailable": "Layanan sedang tidak tersedia. Coba lagi nanti.",
}


def error_response(
    *,
    status_code: int,
    code: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message or _DEFAULT_MESSAGES.get(code, _DEFAULT_MESSAGES["internal_error"]),
            "details": details,
            "request_id": get_request_id(),
        }
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def _format_field_errors(exc: RequestValidationError) -> dict[str, Any]:
    fields: list[dict[str, str]] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query"}]
        fields.append(
            {
                "field": ".".join(location) or "body",
                "reason": str(error.get("msg", "")),
            }
        )
    return {"fields": fields}


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("app_error", code=exc.code, message=exc.message)
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        status_code=400,
        code="validation_error",
        details=_format_field_errors(exc),
    )


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = STATUS_TO_CODE.get(exc.status_code, "internal_error")
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=message if exc.status_code < 500 else None,
        headers=dict(exc.headers or {}),
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error_type=type(exc).__name__)
    return error_response(status_code=500, code="internal_error")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)


def status_to_code(status_code: int) -> str:
    return STATUS_TO_CODE.get(status_code, "internal_error")


def http_status_text(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Unknown"
