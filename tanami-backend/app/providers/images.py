"""Image validation before anything is stored or forwarded.

TQA 9 requires the file type to be checked from content, not from the extension,
the filename to be regenerated server-side, and EXIF (including GPS) to be
stripped before the image is stored. This module is the single place that does
all three, so the scan route and the forum-upload route cannot diverge.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.core.errors import InvalidImage, PayloadTooLarge, UnsupportedMediaType

_ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    extension: str


def validate_and_normalise(
    raw: bytes,
    *,
    max_bytes: int,
    max_side: int,
    max_pixels: int,
) -> ValidatedImage:
    """Decode, bound and re-encode an upload.

    Re-encoding is what strips EXIF: Pillow only writes the pixel data plus a
    fresh, minimal header. The byte budget is checked again after re-encoding
    because a PNG can grow when converted.
    """
    if not raw:
        raise InvalidImage("Berkas foto kosong.")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            image_format = (probe.format or "").upper()
            if image_format not in _ALLOWED_FORMATS:
                raise UnsupportedMediaType(
                    "Format foto tidak didukung. Gunakan JPEG atau PNG.",
                    details={"detected": image_format.lower() or "unknown"},
                )

            width, height = probe.size
            if width * height > max_pixels:
                raise PayloadTooLarge(
                    "Resolusi foto terlalu besar.",
                    details={"width": width, "height": height, "max_pixels": max_pixels},
                )

            probe.load()
            image = probe.copy()

        if max(width, height) > max_side:
            # The client is contracted to compress first (design 11.1), so this
            # is a guard rail, not the normal path.
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if image_format == "PNG":
            image.save(buffer, format="PNG", optimize=True)
        else:
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(buffer, format="JPEG", quality=88, optimize=True, progressive=True)

        encoded = buffer.getvalue()
        if len(encoded) > max_bytes:
            raise PayloadTooLarge(
                "Foto terlalu besar. Kompres ulang lalu coba lagi.",
                details={"bytes": len(encoded), "max_bytes": max_bytes},
            )

        return ValidatedImage(
            data=encoded,
            content_type=_ALLOWED_FORMATS[image_format],
            width=image.width,
            height=image.height,
            extension="png" if image_format == "PNG" else "jpg",
        )
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("Berkas ini sepertinya bukan gambar.") from exc


def new_object_key(prefix: str, *, user_id: str, extension: str) -> str:
    """Server-generated key. The client filename never influences the path."""
    return f"{prefix}/{user_id}/{uuid4().hex}.{extension}"
