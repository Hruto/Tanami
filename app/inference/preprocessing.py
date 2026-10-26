"""Image decoding, validation and quality assessment.

This is the security boundary for anything uploaded to the service:

* the declared content type is ignored; the format is detected from the bytes,
* the decoder is run with a decompression-bomb guard,
* EXIF (including GPS) is dropped because only pixel data is ever kept.

The quality gate is advisory for the *caller*: it never invents a diagnosis.
When the photo is unusable the service reports ``invalid_image`` instead.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Final

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import InvalidImage, PayloadTooLarge, UnsupportedMediaType
from app.domain import QualityStatus

_ALLOWED_FORMATS: Final[frozenset[str]] = frozenset({"JPEG", "PNG"})
_ALLOWED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "application/octet-stream"}
)


@dataclass(frozen=True, slots=True)
class QualityReport:
    blur: QualityStatus
    brightness: QualityStatus

    @property
    def is_usable(self) -> bool:
        return self.blur is QualityStatus.OK and self.brightness is QualityStatus.OK


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """Decoded image ready for the model plus its quality verdict."""

    array: np.ndarray  # float32, shape (H, W, 3), RGB, values in [0, 1]
    width: int
    height: int
    quality: QualityReport


def _laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian, a cheap and standard blur metric."""
    center = gray[1:-1, 1:-1]
    neighbours = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    response = neighbours - 4.0 * center
    return float(response.var())


def assess_quality(rgb: np.ndarray, settings: Settings) -> QualityReport:
    """Judge blur and exposure on the decoded RGB image.

    ``rgb`` is uint8 with shape (H, W, 3). Downscaled to at most 512 px on the
    long side before measuring so the cost is bounded and the blur metric is
    comparable across camera resolutions.
    """
    gray = rgb.astype(np.float32).mean(axis=2)
    height, width = gray.shape
    stride = max(1, max(height, width) // 512)
    sampled = gray[::stride, ::stride]

    if sampled.shape[0] < 3 or sampled.shape[1] < 3:
        return QualityReport(blur=QualityStatus.TOO_BLURRY, brightness=QualityStatus.OK)

    variance = _laplacian_variance(sampled)
    blur = QualityStatus.OK if variance >= settings.blur_min_variance else QualityStatus.TOO_BLURRY

    mean_luminance = float(sampled.mean() / 255.0)
    if mean_luminance < settings.brightness_min:
        brightness = QualityStatus.TOO_DARK
    elif mean_luminance > settings.brightness_max:
        brightness = QualityStatus.TOO_BRIGHT
    else:
        brightness = QualityStatus.OK

    return QualityReport(blur=blur, brightness=brightness)


def decode_and_prepare(
    payload: bytes,
    *,
    content_type: str | None,
    settings: Settings,
    target_size: int,
) -> PreparedImage:
    """Validate, decode, normalise and resize an uploaded image.

    Raises:
        PayloadTooLarge: the body exceeds the configured limit.
        UnsupportedMediaType: the declared type is not an image we accept.
        InvalidImage: the bytes are not a decodable JPEG/PNG of usable size.
    """
    if not payload:
        raise InvalidImage("Gambar kosong.")

    if len(payload) > settings.max_upload_bytes:
        raise PayloadTooLarge(
            "Berkas terlalu besar.",
            details={"max_bytes": settings.max_upload_bytes},
        )

    if content_type is not None and content_type.split(";")[0].strip().lower() not in (
        _ALLOWED_CONTENT_TYPES
    ):
        raise UnsupportedMediaType(
            "Hanya JPEG atau PNG yang didukung.",
            details={"allowed": ["image/jpeg", "image/png"]},
        )

    try:
        with Image.open(io.BytesIO(payload)) as probe:
            image_format = probe.format or ""
            width, height = probe.size
            if image_format.upper() not in _ALLOWED_FORMATS:
                raise UnsupportedMediaType(
                    "Hanya JPEG atau PNG yang didukung.",
                    details={"detected_format": image_format or "unknown"},
                )
            if width * height > settings.max_image_pixels:
                raise PayloadTooLarge(
                    "Resolusi gambar terlalu besar.",
                    details={"max_pixels": settings.max_image_pixels},
                )
            if min(width, height) < settings.min_image_side:
                raise InvalidImage(
                    "Gambar terlalu kecil untuk dianalisis.",
                    details={"min_side": settings.min_image_side},
                )

            probe.draft("RGB", (settings.max_image_side, settings.max_image_side))
            rgb_image = ImageOps.exif_transpose(probe).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImage("Gambar tidak dapat dibaca.") from exc

    if max(rgb_image.size) > settings.max_image_side:
        rgb_image.thumbnail(
            (settings.max_image_side, settings.max_image_side), Image.Resampling.LANCZOS
        )

    rgb = np.asarray(rgb_image, dtype=np.uint8)
    quality = assess_quality(rgb, settings)

    model_image = Image.fromarray(rgb).resize((target_size, target_size), Image.Resampling.BILINEAR)
    array = np.asarray(model_image, dtype=np.float32) / 255.0

    return PreparedImage(
        array=array,
        width=rgb.shape[1],
        height=rgb.shape[0],
        quality=quality,
    )
