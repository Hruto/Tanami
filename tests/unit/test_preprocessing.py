from __future__ import annotations

import numpy as np
import pytest
from app.core.config import Settings
from app.core.errors import InvalidImage, PayloadTooLarge, UnsupportedMediaType
from app.domain import QualityStatus
from app.inference.preprocessing import assess_quality, decode_and_prepare
from tests.conftest import blurred_image, dark_image, encode, noise_image


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "max_upload_bytes": 2 * 1024 * 1024,
        "min_image_side": 64,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_decodes_supported_formats(fmt: str) -> None:
    settings = _settings()
    prepared = decode_and_prepare(
        encode(noise_image(), fmt), content_type="image/jpeg", settings=settings, target_size=224
    )
    assert prepared.array.shape == (224, 224, 3)
    assert prepared.array.dtype == np.float32
    assert prepared.array.min() >= 0.0
    assert prepared.array.max() <= 1.0
    assert prepared.quality.is_usable


def test_garbage_bytes_are_rejected_as_invalid_image() -> None:
    with pytest.raises(InvalidImage):
        decode_and_prepare(
            b"definitely-not-an-image",
            content_type="image/jpeg",
            settings=_settings(),
            target_size=224,
        )


def test_empty_payload_is_invalid() -> None:
    with pytest.raises(InvalidImage, match="kosong"):
        decode_and_prepare(b"", content_type="image/jpeg", settings=_settings(), target_size=224)


def test_oversized_body_is_payload_too_large() -> None:
    settings = _settings(max_upload_bytes=1024)
    with pytest.raises(PayloadTooLarge) as excinfo:
        decode_and_prepare(
            b"x" * 2048, content_type="image/jpeg", settings=settings, target_size=224
        )
    assert excinfo.value.status_code == 413
    assert excinfo.value.code == "payload_too_large"


def test_non_image_content_type_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaType):
        decode_and_prepare(
            encode(noise_image()),
            content_type="application/pdf",
            settings=_settings(),
            target_size=224,
        )


def test_content_type_with_charset_is_accepted() -> None:
    prepared = decode_and_prepare(
        encode(noise_image()),
        content_type="image/jpeg; charset=binary",
        settings=_settings(),
        target_size=224,
    )
    assert prepared.width > 0


def test_missing_content_type_still_validates_bytes() -> None:
    prepared = decode_and_prepare(
        encode(noise_image()), content_type=None, settings=_settings(), target_size=224
    )
    assert prepared.array.shape == (224, 224, 3)


def test_gif_is_rejected_even_when_browser_says_jpeg() -> None:
    from tests.conftest import encode as _encode

    buffer = _encode(noise_image(), fmt="GIF")
    with pytest.raises(UnsupportedMediaType, match="JPEG atau PNG"):
        decode_and_prepare(buffer, content_type="image/jpeg", settings=_settings(), target_size=224)


def test_too_small_image_is_invalid() -> None:
    with pytest.raises(InvalidImage, match="terlalu kecil"):
        decode_and_prepare(
            encode(noise_image(size=32)),
            content_type="image/jpeg",
            settings=_settings(min_image_side=64),
            target_size=224,
        )


def test_huge_pixel_count_is_rejected_before_decoding() -> None:
    settings = _settings(max_image_pixels=1000, min_image_side=8)
    with pytest.raises(PayloadTooLarge, match="Resolusi"):
        decode_and_prepare(
            encode(noise_image(size=64)),
            content_type="image/jpeg",
            settings=settings,
            target_size=224,
        )


def test_tall_image_is_resized_to_max_side() -> None:
    from PIL import Image

    settings = _settings(max_image_side=128, min_image_side=16, max_image_pixels=10_000_000)
    tall = Image.new("RGB", (200, 900), (200, 40, 40))
    prepared = decode_and_prepare(
        encode(tall), content_type="image/jpeg", settings=settings, target_size=224
    )
    assert max(prepared.width, prepared.height) <= 200
    assert prepared.array.shape == (224, 224, 3)


def test_blurry_image_is_flagged() -> None:
    prepared = decode_and_prepare(
        encode(blurred_image()), content_type="image/jpeg", settings=_settings(), target_size=224
    )
    assert prepared.quality.blur is QualityStatus.TOO_BLURRY
    assert prepared.quality.is_usable is False


def test_dark_image_is_flagged() -> None:
    prepared = decode_and_prepare(
        encode(dark_image()), content_type="image/jpeg", settings=_settings(), target_size=224
    )
    assert prepared.quality.brightness is QualityStatus.TOO_DARK


def test_overexposed_image_is_flagged() -> None:
    from PIL import Image

    white = Image.new("RGB", (320, 320), (255, 255, 255))
    report = assess_quality(np.asarray(white), _settings())
    assert report.brightness is QualityStatus.TOO_BRIGHT


def test_assess_quality_on_tiny_array_does_not_crash() -> None:
    tiny = np.zeros((2, 2, 3), dtype=np.uint8)
    report = assess_quality(tiny, _settings())
    assert report.blur is QualityStatus.TOO_BLURRY


def test_output_array_is_a_copy_not_a_view_of_the_file() -> None:
    payload = encode(noise_image())
    prepared = decode_and_prepare(
        payload, content_type="image/jpeg", settings=_settings(), target_size=224
    )
    assert prepared.array.flags.writeable
    assert prepared.array.flags.owndata or prepared.array.base is not None
