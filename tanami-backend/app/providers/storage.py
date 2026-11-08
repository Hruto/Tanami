"""Object storage abstractions.

Images never go into PostgreSQL (TQA 3): the database stores only ``image_key``.
Two implementations share the interface:

``S3Storage``
    Any S3-compatible service (Cloudflare R2, MinIO, AWS S3).
``MemoryStorage``
    A dict for tests and local dry runs. It refuses to be used in production,
    where ``Settings`` already rejects the configuration.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.core.errors import ServiceUnavailable
from app.core.logging import get_logger

logger = get_logger("storage")


class StorageProvider(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    def public_url(self, key: str) -> str: ...


class MemoryStorage:
    """In-process storage. Content is discarded when the process exits."""

    def __init__(self, public_base_url: str = "/media") -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._public_base_url = public_base_url.rstrip("/")

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = (data, content_type)

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._objects

    def public_url(self, key: str) -> str:
        return f"{self._public_base_url}/{key}"

    def get(self, key: str) -> bytes | None:
        """Test helper: read what was stored."""
        entry = self._objects.get(key)
        return entry[0] if entry else None

    def entry(self, key: str) -> tuple[bytes, str] | None:
        """Bytes and content type, for the local ``/media`` route."""
        return self._objects.get(key)

    @property
    def keys(self) -> list[str]:
        return sorted(self._objects)


class S3Storage:
    """S3-compatible storage.

    boto3 is synchronous, so calls run in a worker thread; a scan request is
    already dominated by inference and this keeps the event loop free.
    """

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=15,
            ),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl="private, max-age=31536000, immutable",
                # Server-side encryption is a no-op on providers without KMS but
                # harmless on those that support it.
                ServerSideEncryption="AES256",
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("storage_put_failed", key=key, error=str(exc))
            raise ServiceUnavailable("Penyimpanan foto sedang tidak tersedia.") from exc

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            # Deleting is best-effort during account removal; a stale object is
            # far less harmful than failing the whole request.
            logger.error("storage_delete_failed", key=key, error=str(exc))

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            logger.error("storage_head_failed", key=key, error=str(exc))
            raise ServiceUnavailable("Penyimpanan foto sedang tidak tersedia.") from exc
        except BotoCoreError as exc:
            logger.error("storage_head_failed", key=key, error=str(exc))
            raise ServiceUnavailable("Penyimpanan foto sedang tidak tersedia.") from exc
        return True

    def public_url(self, key: str) -> str:
        if self._settings.s3_public_base_url:
            return f"{self._settings.s3_public_base_url.rstrip('/')}/{key}"
        try:
            url: str = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=self._settings.s3_presign_ttl_seconds,
            )
            return url
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - config error
            logger.error("storage_presign_failed", key=key, error=str(exc))
            return f"{self._settings.s3_endpoint_url.rstrip('/')}/{self._bucket}/{key}"


def build_storage(settings: Settings) -> StorageProvider:
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return MemoryStorage()
