"""Scan orchestration: the only place that owns the full scan lifecycle.

Order of operations matters and is deliberate:

1. Idempotency check *before* spending an upload or an inference. A resend with
   the same ``client_uuid`` returns the stored row and never calls the model
   (``design.md`` 10.6, 14).
2. Decode and re-encode the image (strips EXIF/GPS, enforces size and type).
3. Store the image, then call vision. If vision fails the object is deleted, so
   a failed scan does not leave an orphan image.
4. Persist the result with the advice block taken from the reviewed knowledge
   base (the ``diseases`` table), never from the model (TQA 8.3).
5. Re-derive plant health and the absolute harvest window from the plant's
   scans *in capture order*. Replaying rather than applying the newest result
   incrementally is what keeps the status right when the offline queue
   (design 14) delivers an old photo after a newer one, or a scan is deleted.

The plant side effects only run when the scan is attached to a plant; an
unlinked scan is still stored, listed and can receive feedback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, ValidationError
from app.core.logging import get_logger
from app.core.metrics import SCAN_LATENCY, SCANS_TOTAL
from app.core.pagination import Cursor
from app.domain import (
    DETECTION_COMMODITIES,
    DISEASE_LABELS,
    RIPENESS_LABELS,
    CauseCategory,
    HealthStatus,
    ResultStatus,
    ScanType,
    Severity,
)
from app.models.content import Disease
from app.models.farm import Farm, Plant
from app.models.scan import Scan, ScanFeedback
from app.providers.images import ValidatedImage, new_object_key, validate_and_normalise
from app.providers.storage import StorageProvider
from app.providers.vision import VisionClient
from app.schemas.scan import FeedbackOut, ScanCreated, ScanDetailOut

logger = get_logger("scan")

# How many disease scans are replayed to derive a plant's health. Far more than
# the rules ever look back, and it bounds the query on a plant scanned daily.
_HEALTH_REPLAY_LIMIT = 50
_NAMED_STATUSES = frozenset({ResultStatus.CONFIDENT.value, ResultStatus.UNCERTAIN.value})


@dataclass(frozen=True, slots=True)
class ScanCommand:
    user_id: UUID
    scan_type: ScanType
    image: bytes
    client_uuid: UUID
    captured_at: datetime | None
    plant_id: UUID | None
    detection_plant_id: UUID | None = None


# --------------------------------------------------------------------------- #
# Pure rules (design 8.2) - unit-tested without a database
# --------------------------------------------------------------------------- #
def next_health_status(
    previous: str,
    *,
    status: str,
    cause: str | None,
    severity: str | None,
) -> str:
    """One step of the plant health state machine in ``design.md`` 8.2.

    * a confident named disease -> ``sick``, or ``at_risk`` when the model says
      the case is mild ("penyakit ringan")
    * ``uncertain`` -> ``at_risk``
    * a confident healthy scan -> ``recovering`` if the plant was ``sick``;
      ``healthy`` once a second consecutive healthy scan arrives (``recovering``
      -> ``healthy``), and ``healthy`` straight away otherwise
    * ``unknown`` / ``invalid_image`` say nothing about the plant: keep the
      previous status.
    """
    if status == ResultStatus.CONFIDENT.value and cause not in {
        None,
        CauseCategory.HEALTHY.value,
        CauseCategory.UNKNOWN.value,
    }:
        if severity == Severity.MILD.value:
            return HealthStatus.AT_RISK.value
        return HealthStatus.SICK.value

    if status == ResultStatus.UNCERTAIN.value:
        return HealthStatus.AT_RISK.value

    if status == ResultStatus.CONFIDENT.value and cause == CauseCategory.HEALTHY.value:
        if previous == HealthStatus.SICK.value:
            return HealthStatus.RECOVERING.value
        return HealthStatus.HEALTHY.value

    return previous


def replay_health_status(scans: list[tuple[str, dict[str, Any]]]) -> str:
    """Fold ``(status, result)`` pairs, oldest first, into a health status."""
    current = HealthStatus.UNKNOWN.value
    for status, result in scans:
        top = result.get("top")
        cause = top.get("cause_category") if isinstance(top, dict) else None
        severity = result.get("severity")
        current = next_health_status(
            current,
            status=status,
            cause=str(cause) if cause is not None else None,
            severity=str(severity) if severity is not None else None,
        )
    return current


class ScanService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        storage: StorageProvider,
        vision: VisionClient,
    ) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage
        self.vision = vision

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #
    async def create(self, command: ScanCommand) -> ScanCreated:
        started = time.perf_counter()
        existing = await self._find_by_client_uuid(command.user_id, command.client_uuid)
        if existing is not None:
            if existing.scan_type != command.scan_type.value:
                raise Conflict(
                    "client_uuid ini sudah dipakai untuk jenis scan lain.",
                    details={"field": "client_uuid", "existing_type": existing.scan_type},
                )
            return self._to_created(existing, is_duplicate=True)

        detection = None
        if command.detection_plant_id is not None:
            from app.services.detection import DetectionService

            detection = await DetectionService(
                self.session, self.settings, self.storage
            ).get_active(command.user_id, command.detection_plant_id)
        plant_id = command.plant_id or (detection.plant_id if detection else None)
        plant = await self._resolve_plant(
            command.user_id, plant_id, linked=command.plant_id is None
        )
        captured_at = self._captured_at(command.captured_at)
        validated = self._validate_image(command.image)
        image_key = new_object_key(
            "scans", user_id=str(command.user_id), extension=validated.extension
        )
        await self.storage.put(image_key, validated.data, validated.content_type)

        try:
            prediction = await self.vision.predict(
                scan_type=command.scan_type.value,
                image=validated.data,
                content_type=validated.content_type,
                client_uuid=str(command.client_uuid),
                commodity_code=(
                    detection.commodity_code
                    if detection
                    else plant.commodity_code
                    if plant and plant.commodity_code in DETECTION_COMMODITIES
                    else "chili"
                ),
            )
        except Exception:
            # Never leave an image behind for a scan that does not exist.
            await self.storage.delete(image_key)
            raise

        disease = await self._known_disease(command.scan_type, prediction.status, prediction.result)
        result = self._enrich_result(
            scan_type=command.scan_type,
            status=prediction.status,
            result=prediction.result,
            quality=prediction.quality,
            captured_at=captured_at,
            disease=disease,
        )

        scan = Scan(
            id=uuid4(),
            user_id=command.user_id,
            plant_id=plant.id if plant else None,
            detection_plant_id=detection.id if detection else None,
            scan_type=command.scan_type.value,
            image_key=image_key,
            image_content_type=validated.content_type,
            client_uuid=command.client_uuid,
            captured_at=captured_at,
            status=prediction.status,
            model_version=prediction.model_version,
            result=result,
            disease_code=disease.code if disease else None,
            quality=prediction.quality,
            confidence=prediction.confidence,
            commodity_code=prediction.commodity_code,
            inference_ms=prediction.inference_ms,
        )
        self.session.add(scan)

        try:
            await self.session.flush()
        except IntegrityError:
            # Two parallel uploads with the same client_uuid: the loser reads the
            # winner's row instead of surfacing a 500.
            await self.session.rollback()
            await self.storage.delete(image_key)
            winner = await self._find_by_client_uuid(command.user_id, command.client_uuid)
            if winner is None:
                raise
            return self._to_created(winner, is_duplicate=True)

        if plant is not None:
            await self.refresh_plant(plant)

        await self.session.commit()

        SCANS_TOTAL.labels(scan_type=scan.scan_type, status=scan.status).inc()
        SCAN_LATENCY.labels(scan_type=scan.scan_type).observe(time.perf_counter() - started)
        logger.info(
            "scan_created",
            scan_id=str(scan.id),
            scan_type=scan.scan_type,
            status=scan.status,
            model_version=scan.model_version,
            plant_id=str(scan.plant_id) if scan.plant_id else None,
        )
        return self._to_created(scan, is_duplicate=False)

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    async def get(self, user_id: UUID, scan_id: UUID) -> Scan:
        scan = await self.session.get(Scan, scan_id)
        if scan is None or scan.user_id != user_id:
            raise NotFound("Scan tidak ditemukan.")
        return scan

    async def get_detail(self, user_id: UUID, scan_id: UUID) -> ScanDetailOut:
        scan = await self.get(user_id, scan_id)
        feedback = (
            await self.session.execute(select(ScanFeedback).where(ScanFeedback.scan_id == scan.id))
        ).scalar_one_or_none()
        return self.detail_out(scan, feedback)

    async def list(
        self,
        user_id: UUID,
        *,
        plant_id: UUID | None = None,
        detection_plant_id: UUID | None = None,
        scan_type: ScanType | None = None,
        limit: int,
        cursor: Cursor | None,
    ) -> list[Scan]:
        """Newest first, keyset-paginated on ``(created_at, id)``.

        ``limit`` is the caller's page size plus one: the extra row is how the
        route learns whether another page exists without a second count query.
        """
        statement = select(Scan).where(Scan.user_id == user_id)
        if detection_plant_id is not None:
            statement = statement.where(Scan.detection_plant_id == detection_plant_id)
        if plant_id is not None:
            statement = statement.where(Scan.plant_id == plant_id)
        if scan_type is not None:
            statement = statement.where(Scan.scan_type == scan_type.value)
        if cursor is not None:
            statement = statement.where(
                or_(
                    Scan.created_at < cursor.created_at,
                    and_(
                        Scan.created_at == cursor.created_at,
                        Scan.id < cursor.last_id,
                    ),
                )
            )
        statement = statement.order_by(Scan.created_at.desc(), Scan.id.desc()).limit(limit)
        return list((await self.session.execute(statement)).scalars())

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #
    async def delete(self, user_id: UUID, scan_id: UUID) -> None:
        scan = await self.get(user_id, scan_id)
        image_key = scan.image_key
        plant_id = scan.plant_id
        await self.session.delete(scan)
        await self.session.flush()
        if plant_id is not None:
            plant = await self.session.get(Plant, plant_id)
            if plant is not None:
                await self.refresh_plant(plant)
        await self.session.commit()
        # The row is gone first: an orphaned object is recoverable, a row that
        # points at a missing object is a broken history entry.
        await self.storage.delete(image_key)

    async def upsert_feedback(
        self,
        user_id: UUID,
        scan_id: UUID,
        *,
        value: str,
        comment: str | None,
    ) -> ScanFeedback:
        scan = await self.get(user_id, scan_id)
        existing = (
            await self.session.execute(select(ScanFeedback).where(ScanFeedback.scan_id == scan.id))
        ).scalar_one_or_none()

        if existing is None:
            feedback = ScanFeedback(
                id=uuid4(),
                scan_id=scan.id,
                user_id=user_id,
                value=value,
                comment=comment,
            )
            self.session.add(feedback)
        else:
            existing.value = value
            existing.comment = comment
            feedback = existing

        await self.session.commit()
        await self.session.refresh(feedback)
        return feedback

    async def attach_plant(self, user_id: UUID, scan_id: UUID, plant_id: UUID | None) -> Scan:
        scan = await self.get(user_id, scan_id)
        previous_plant_id = scan.plant_id
        plant = await self._resolve_plant(user_id, plant_id) if plant_id else None
        scan.plant_id = plant.id if plant else None
        await self.session.flush()

        # Both the old and the new plant may have changed status.
        for affected_id in {previous_plant_id, scan.plant_id} - {None}:
            affected = await self.session.get(Plant, affected_id)
            if affected is not None:
                await self.refresh_plant(affected)
        await self.session.commit()
        return scan

    async def refresh_plant(self, plant: Plant) -> None:
        """Recompute ``health_status`` and the harvest window from stored scans."""
        disease_rows = (
            await self.session.execute(
                select(Scan.status, Scan.result)
                .where(Scan.plant_id == plant.id, Scan.scan_type == ScanType.DISEASE.value)
                .order_by(Scan.captured_at.desc(), Scan.created_at.desc())
                .limit(_HEALTH_REPLAY_LIMIT)
            )
        ).all()
        history = [(str(status), dict(result)) for status, result in reversed(disease_rows)]
        plant.health_status = replay_health_status(history)

        ripeness_rows = (
            await self.session.execute(
                select(Scan.result)
                .where(Scan.plant_id == plant.id, Scan.scan_type == ScanType.RIPENESS.value)
                .order_by(Scan.captured_at.desc(), Scan.created_at.desc())
                .limit(10)
            )
        ).scalars()
        window: tuple[date, date] | None = None
        for result in ripeness_rows:
            start = result.get("estimated_harvest_date_min")
            end = result.get("estimated_harvest_date_max")
            if isinstance(start, str) and isinstance(end, str):
                window = (date.fromisoformat(start), date.fromisoformat(end))
                break
        plant.expected_harvest_min = window[0] if window else None
        plant.expected_harvest_max = window[1] if window else None

    # ------------------------------------------------------------------ #
    # Mapping
    # ------------------------------------------------------------------ #
    def scan_fields(self, scan: Scan) -> dict[str, Any]:
        return scan_fields(scan, self.storage)

    def detail_out(self, scan: Scan, feedback: ScanFeedback | None) -> ScanDetailOut:
        return ScanDetailOut(
            **self.scan_fields(scan),
            commodity_code=scan.commodity_code,
            feedback=feedback_out(feedback),
        )

    def _to_created(self, scan: Scan, *, is_duplicate: bool) -> ScanCreated:
        return ScanCreated(**self.scan_fields(scan), is_duplicate=is_duplicate)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _find_by_client_uuid(self, user_id: UUID, client_uuid: UUID) -> Scan | None:
        result = await self.session.execute(
            select(Scan).where(Scan.user_id == user_id, Scan.client_uuid == client_uuid)
        )
        return result.scalar_one_or_none()

    async def _resolve_plant(
        self, user_id: UUID, plant_id: UUID | None, *, linked: bool = False
    ) -> Plant | None:
        """The tracked plant a scan belongs to.

        ``linked`` means the id came from the detection plant rather than the
        request: then a tracked plant whose tracking has ended is silently
        skipped instead of rejecting the detection.
        """
        if plant_id is None:
            return None
        if linked:
            candidate = await self.session.get(Plant, plant_id)
            if candidate is None or candidate.ended_at is not None:
                return None
        plant = await self.session.get(Plant, plant_id)
        if plant is None:
            raise NotFound("Tanaman tidak ditemukan.")
        farm = await self.session.get(Farm, plant.farm_id)
        if farm is None or farm.user_id != user_id:
            # Same message for "does not exist" and "belongs to someone else".
            raise NotFound("Tanaman tidak ditemukan.")
        if plant.ended_at is not None:
            raise ValidationError(
                "Tracking tanaman ini sudah diakhiri.", details={"field": "plant_id"}
            )
        return plant

    async def _known_disease(
        self, scan_type: ScanType, status: str, result: dict[str, object]
    ) -> Disease | None:
        """The knowledge-base row for the top prediction, if there is one.

        A model can ship a class before the editorial team has written and
        reviewed its row. Storing that code would violate the ``disease_code``
        foreign key, and inventing advice for it would break TQA 8.3, so the
        scan is stored without a disease link and without advice instead.
        """
        if scan_type is not ScanType.DISEASE or status not in _NAMED_STATUSES:
            return None
        top = result.get("top")
        code = top.get("disease_code") if isinstance(top, dict) else None
        if not code:
            return None
        disease = (
            await self.session.execute(select(Disease).where(Disease.code == str(code)))
        ).scalar_one_or_none()
        if disease is None:
            logger.warning("scan_unknown_disease_code", disease_code=str(code))
        return disease

    def _validate_image(self, raw: bytes) -> ValidatedImage:
        return validate_and_normalise(
            raw,
            max_bytes=self.settings.max_scan_upload_bytes,
            max_side=self.settings.max_image_side,
            max_pixels=self.settings.max_image_pixels,
        )

    def _captured_at(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(UTC)
        now = datetime.now(UTC)
        if value > now + timedelta(minutes=5):
            raise ValidationError(
                "Waktu foto tidak boleh di masa depan.", details={"field": "captured_at"}
            )
        if value < now - timedelta(days=30):
            raise ValidationError(
                "Waktu foto terlalu lama. Kirim ulang foto terbaru.",
                details={"field": "captured_at"},
            )
        return value

    def _enrich_result(
        self,
        *,
        scan_type: ScanType,
        status: str,
        result: dict[str, object],
        quality: dict[str, object],
        captured_at: datetime,
        disease: Disease | None,
    ) -> dict[str, object]:
        """Add what the vision contract deliberately leaves to the backend."""
        enriched = dict(result)
        if scan_type is ScanType.DISEASE:
            top = enriched.get("top")
            confidence = top.get("confidence") if isinstance(top, dict) else None
            # Requirement 3 shows the confidence as a percentage.
            enriched["confidence_percent"] = (
                round(float(confidence) * 100) if isinstance(confidence, int | float) else None
            )
            enriched["advice"] = (
                advice_from_knowledge_base(disease, status=status) if disease else None
            )
            enriched["quality"] = quality
            return enriched

        stage = enriched.get("stage")
        if isinstance(stage, str) and not enriched.get("stage_label"):
            enriched["stage_label"] = RIPENESS_LABELS.get(stage, stage)
        days_min = enriched.get("estimated_days_min")
        days_max = enriched.get("estimated_days_max")
        if isinstance(days_min, int) and isinstance(days_max, int):
            # The estimate is relative to when the photo was taken, not when an
            # offline queue finally delivered it (design 12.4).
            base = captured_at.date()
            enriched["estimated_harvest_date_min"] = (base + timedelta(days=days_min)).isoformat()
            enriched["estimated_harvest_date_max"] = (base + timedelta(days=days_max)).isoformat()
        else:
            enriched["estimated_harvest_date_min"] = None
            enriched["estimated_harvest_date_max"] = None
        return enriched


def scan_fields(scan: Scan, storage: StorageProvider) -> dict[str, Any]:
    return {
        "id": str(scan.id),
        "type": ScanType(scan.scan_type),
        "status": ResultStatus(scan.status),
        "model_version": scan.model_version,
        "image_url": storage.public_url(scan.image_key),
        "plant_id": str(scan.plant_id) if scan.plant_id else None,
        "detection_plant_id": str(scan.detection_plant_id) if scan.detection_plant_id else None,
        "captured_at": scan.captured_at,
        "result": dict(scan.result),
        "quality": dict(scan.quality),
        "created_at": scan.created_at,
    }


def advice_from_knowledge_base(disease: Disease, *, status: str) -> dict[str, object]:
    """The ``advice`` block of design 11.3, built only from a reviewed row.

    ``first_aid`` is the short solution the confident result card shows
    (design 11.4); the reviewer and date are what TQA 8.3 requires next to every
    recommendation.
    """
    treatments = disease.treatments if isinstance(disease.treatments, dict) else {}
    first_aid_raw = treatments.get("first_aid")
    first_aid = [str(item) for item in first_aid_raw][:3] if isinstance(first_aid_raw, list) else []

    if disease.cause_category == CauseCategory.HEALTHY.value:
        summary = "Daun tampak sehat. Pertahankan perawatan dan pemeriksaan rutin."
    elif status == ResultStatus.UNCERTAIN.value:
        summary = (
            f"Kemungkinan {disease.name_id.lower()}, tetapi kami belum sepenuhnya yakin. "
            "Coba foto ulang atau tanyakan ke ahli."
        )
    else:
        summary = f"Daun tampak terkena {disease.name_id.lower()}."

    return {
        "summary": summary,
        "disease_name": disease.name_id,
        "symptoms": disease.symptoms,
        "treatments": treatments,
        "disease_detail_url": f"/diseases/{disease.code}",
        "first_aid": first_aid,
        "reviewed_by": disease.reviewed_by,
        "reviewed_at": disease.reviewed_at.isoformat() if disease.reviewed_at else None,
    }


def feedback_out(feedback: ScanFeedback | None) -> FeedbackOut | None:
    if feedback is None:
        return None
    return FeedbackOut(
        value=feedback.value,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


def disease_label(code: str) -> str:
    return DISEASE_LABELS.get(code, code)


def ripeness_label(stage: str) -> str:
    return RIPENESS_LABELS.get(stage, stage)


__all__ = [
    "ScanCommand",
    "ScanService",
    "advice_from_knowledge_base",
    "disease_label",
    "feedback_out",
    "next_health_status",
    "replay_health_status",
    "ripeness_label",
]
