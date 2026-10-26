from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from app.api.deps import PredictServiceDep, SettingsDep, require_service_token
from app.core.errors import ValidationError
from app.domain import ScanType
from app.schemas.prediction import ErrorResponse, PredictionResponse
from app.services.predict import PredictCommand

router = APIRouter(prefix="/v1", tags=["predict"])

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="client_uuid dari aplikasi, untuk korelasi log.",
    ),
]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "validation_error"},
    401: {"model": ErrorResponse, "description": "unauthorized"},
    413: {"model": ErrorResponse, "description": "payload_too_large"},
    415: {"model": ErrorResponse, "description": "unsupported_media_type"},
    422: {"model": ErrorResponse, "description": "invalid_image"},
    429: {"model": ErrorResponse, "description": "rate_limited (dari backend)"},
    500: {"model": ErrorResponse, "description": "internal_error"},
    503: {"model": ErrorResponse, "description": "service_unavailable"},
}


@router.post(
    "/predict",
    response_model=PredictionResponse,
    dependencies=[Depends(require_service_token)],
    summary="Klasifikasi satu gambar",
    description=(
        "Menerima satu foto daun (type=disease) atau buah (type=ripeness) dan "
        "mengembalikan `result` sesuai design.md 11.3 beserta `status` dari "
        "ambang keyakinan design.md 11.2.\n\n"
        "Layanan ini **stateless**: tidak menyimpan gambar, tidak menulis "
        "database, tidak mengirim notifikasi. Penyimpanan dan pemberian "
        "rekomendasi tetap di backend."
    ),
    responses=_ERRORS,
)
async def predict(
    settings: SettingsDep,
    service: PredictServiceDep,
    type: Annotated[ScanType, Form(description="disease atau ripeness")],
    image: Annotated[UploadFile, File(description="JPEG/PNG, maks 2 MB dari backend")],
    client_uuid: Annotated[str | None, Form(description="UUID dari klien")] = None,
    commodity_code: Annotated[str | None, Form(description="Default: komoditas aktif")] = None,
    idempotency_key: IdempotencyKey = None,
) -> PredictionResponse:
    commodity = (commodity_code or settings.commodity_code).strip()
    if commodity not in settings.supported_commodities:
        raise ValidationError(
            "Komoditas belum didukung.",
            details={
                "field": "commodity_code",
                "supported": list(settings.supported_commodities),
            },
        )

    payload = await image.read()
    data = await service.predict(
        PredictCommand(
            scan_type=type,
            image_bytes=payload,
            content_type=image.content_type,
            commodity_code=commodity,
            client_uuid=client_uuid or idempotency_key,
        )
    )
    return PredictionResponse(data=data)
