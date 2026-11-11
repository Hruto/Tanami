"""Application errors and the wire envelope from ``design.md`` 10.1.

The class attributes carry the contract: status code, machine code and the
Indonesian message the app may show to a farmer. Handlers in
``app.core.handlers`` turn any ``AppError`` into the envelope, so a service can
raise without knowing anything about HTTP.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Terjadi kesalahan pada server."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
    default_message = "Data yang dikirim tidak valid."


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Sesi Anda tidak valid atau sudah berakhir."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "Anda tidak memiliki akses ke data ini."


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Data tidak ditemukan."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Data sudah ada."


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"
    default_message = "Foto terlalu besar. Kompres ulang lalu coba lagi."


class UnsupportedMediaType(AppError):
    status_code = 415
    code = "unsupported_media_type"
    default_message = "Tipe berkas tidak didukung. Gunakan JPEG atau PNG."


class InvalidImage(AppError):
    status_code = 422
    code = "invalid_image"
    default_message = "Gambar tidak dapat diproses. Coba foto ulang."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Terlalu sering. Tunggu sebentar lalu coba lagi."


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
    default_message = "Layanan sedang tidak tersedia. Coba lagi nanti."


STATUS_TO_CODE: dict[int, str] = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "validation_error",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "invalid_image",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}
