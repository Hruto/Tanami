"""Image validation, tokens, pagination cursors and the BMKG parser."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.errors import InvalidImage, PayloadTooLarge, UnsupportedMediaType, ValidationError
from app.core.pagination import decode_cursor, encode_cursor, page_request
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.providers.images import validate_and_normalise
from app.providers.weather import _parse_bmkg
from PIL import Image

from tests.helpers import image_bytes, text_bytes

LIMITS = {"max_bytes": 2_097_152, "max_side": 1280, "max_pixels": 40_000_000}
SECRET = "unit-test-secret-0123456789-0123456789"


def jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (64, 64), (10, 140, 30))
    exif = Image.Exif()
    exif[0x8825] = {2: (6.0, 10.0, 30.0)}  # GPSInfo
    exif[0x010F] = "PhoneMaker"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def test_exif_and_gps_are_stripped() -> None:
    raw = jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif()
    clean = validate_and_normalise(raw, **LIMITS)
    assert clean.content_type == "image/jpeg"
    assert not Image.open(io.BytesIO(clean.data)).getexif()


def test_oversized_side_is_downscaled() -> None:
    clean = validate_and_normalise(image_bytes(3000, 1500), **LIMITS)
    assert max(clean.width, clean.height) == 1280


def test_png_is_kept_as_png() -> None:
    assert validate_and_normalise(image_bytes(fmt="PNG"), **LIMITS).extension == "png"


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (b"", InvalidImage),
        (text_bytes(), InvalidImage),
        (image_bytes(fmt="GIF"), UnsupportedMediaType),
    ],
)
def test_rejected_uploads(raw: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        validate_and_normalise(raw, **LIMITS)


def test_pixel_bomb_is_rejected() -> None:
    with pytest.raises(PayloadTooLarge):
        validate_and_normalise(
            image_bytes(400, 400), max_bytes=10**7, max_side=1280, max_pixels=1000
        )


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("sandi-keren-123")
    assert verify_password("sandi-keren-123", hashed)
    assert not verify_password("salah", hashed)
    assert not verify_password("x", "not-a-hash")


def test_access_token_roundtrip_and_expiry() -> None:
    user_id = uuid4()
    token, _ = create_access_token(
        user_id=user_id,
        role="farmer",
        session_id="sid",
        secret=SECRET,
        algorithm="HS256",
        issuer="tanami",
        ttl_seconds=60,
    )
    claims = decode_access_token(token, secret=SECRET, algorithm="HS256", issuer="tanami")
    assert claims.user_id == user_id
    expired, _ = create_access_token(
        user_id=user_id,
        role="farmer",
        session_id="sid",
        secret=SECRET,
        algorithm="HS256",
        issuer="tanami",
        ttl_seconds=60,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    with pytest.raises(TokenError):
        decode_access_token(expired, secret=SECRET, algorithm="HS256", issuer="tanami")
    with pytest.raises(TokenError):
        decode_access_token(
            token, secret="another-secret-0123456789-0123456789", algorithm="HS256", issuer="tanami"
        )


def test_cursor_roundtrip_and_validation() -> None:
    moment, row_id = datetime(2026, 11, 7, 1, 2, 3, tzinfo=UTC), uuid4()
    cursor = decode_cursor(encode_cursor(moment, row_id))
    assert (cursor.created_at, cursor.last_id) == (moment, row_id)
    with pytest.raises(ValidationError):
        decode_cursor("bukan-kursor")
    with pytest.raises(ValidationError):
        page_request(51, None)
    assert page_request(None, None).limit == 20


def test_bmkg_parser_groups_days_and_reads_precipitation() -> None:
    payload = {
        "data": [
            {
                "cuaca": [
                    [
                        {
                            "local_datetime": "2026-11-07 07:00:00",
                            "t": 27,
                            "hu": 88,
                            "weather_desc": "Berawan",
                            "ws": 8.4,
                            "wd": "TL",
                            "tp": 0.4,
                        },
                        {
                            "local_datetime": "2026-11-07 10:00:00",
                            "t": "29",
                            "hu": 80,
                            "weather_desc": "Hujan Ringan",
                            "ws": 9,
                            "wd": "T",
                            "tp": 1.2,
                        },
                    ],
                    [
                        {
                            "local_datetime": "2026-11-08 07:00:00",
                            "t": 26,
                            "hu": 91,
                            "weather_desc": "Hujan Lebat",
                        }
                    ],
                    ["ignored", {"no_datetime": True}],
                ]
            }
        ]
    }
    days = _parse_bmkg(payload)
    assert [day.date for day in days] == ["2026-11-07", "2026-11-08"]
    assert days[0].slots[1].temperature_c == 29.0
    assert days[0].slots[1].precipitation_mm == 1.2
    assert days[1].slots[0].precipitation_mm is None
    assert _parse_bmkg({"data": "nope"}) == []
