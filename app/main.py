"""FastAPI application factory.

Everything that touches the outside world (settings, model loading, middleware,
exception mapping) is wired here, so ``create_app`` is the single place tests
need to look to understand the process lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import ops, predict
from app.core.config import Settings
from app.core.errors import STATUS_TO_CODE, AppError
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.state import AppState
from app.services.predict import PredictService
from app.services.registry import ModelRegistry

logger = get_logger(__name__)

_DESCRIPTION = """
Layanan inferensi Tanami. **Stateless** dan **tanpa database**.

Backend Tanami memanggil layanan ini setelah memvalidasi unggahan pengguna,
lalu menyimpan hasil, menggabungkan rekomendasi dari tabel `diseases`, dan
mengirim notifikasi. Kontrak piksel-demi-piksel mengikuti `design.md`
bagian 11; lihat `contracts/API.md` untuk ringkasan yang bisa disepakati tim.
"""


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
        headers=headers,
    )


def create_app(settings: Settings | None = None, *, load_models: bool = True) -> FastAPI:
    resolved = settings or Settings()
    configure_logging(resolved.log_level, json_output=resolved.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry = ModelRegistry(resolved)
        if load_models:
            registry.load()
        # Built once so its CapacityLimiter is shared by every request; a
        # per-request service would give each request its own limiter and
        # silently disable VISION_MAX_CONCURRENT_INFERENCE.
        predict_service = PredictService(resolved, registry)
        app.state.tanami = AppState(
            settings=resolved,
            registry=registry,
            predict_service=predict_service,
        )
        if load_models and not registry.is_ready:
            logger.error("service_started_degraded", errors=registry.load_errors)
        else:
            logger.info("service_started", environment=resolved.app_env)
        yield
        logger.info("service_stopped")

    app = FastAPI(
        title="Tanami Vision",
        version=__version__,
        description=_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs" if resolved.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.docs_enabled else None,
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(ops.router)
    app.include_router(predict.router)

    # ---------------------------------------------------------------- errors
    from app.core.context import get_request_id

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            exc.status_code,
            exc.code,
            exc.message,
            details=exc.details,
            headers=exc.headers,
            request_id=get_request_id(),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {
            "fields": [
                {
                    "loc": [str(part) for part in error.get("loc", ())],
                    "type": str(error.get("type", "")),
                    "msg": str(error.get("msg", "")),
                }
                for error in exc.errors()
            ]
        }
        return _error_response(
            400,
            "validation_error",
            "Data yang dikirim tidak valid.",
            details=details,
            request_id=get_request_id(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(
            exc.status_code,
            STATUS_TO_CODE.get(exc.status_code, "internal_error"),
            str(exc.detail),
            headers=dict(exc.headers) if exc.headers else None,
            request_id=get_request_id(),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # The traceback goes to the structured log, never to the caller.
        logger.exception("unhandled_error", error=str(exc))
        return _error_response(
            500,
            "internal_error",
            "Terjadi kesalahan pada layanan.",
            request_id=get_request_id(),
        )

    return app
