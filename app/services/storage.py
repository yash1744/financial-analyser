"""Object storage behind a small protocol.

Receipt images go to Cloudflare R2 in real deployments (S3-compatible;
boto3 is synchronous, so calls run in a thread). The local backend keeps
development free of cloud credentials by writing under a directory.
Keys are always generated server-side (uuid-based) — never derived from
client-supplied names.
"""

import asyncio
import logging
from pathlib import Path
from typing import Protocol

import boto3

from app.core.config import Settings

logger = logging.getLogger(__name__)


class StorageConfigurationError(Exception):
    """Object storage credentials are missing or invalid. Maps to 503."""


class ObjectNotFoundError(Exception):
    """The requested object does not exist in storage."""


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class R2ObjectStorage:
    """Cloudflare R2 via its S3-compatible API."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.r2_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
            except self._client.exceptions.NoSuchKey as exc:
                raise ObjectNotFoundError(key) from exc
            return response["Body"].read()

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        # S3/R2 DeleteObject is idempotent — deleting a missing key succeeds
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=key
        )


class LocalObjectStorage:
    """Filesystem-backed storage for development. Keys are server-generated
    uuid paths, so traversal via key content cannot occur; the resolved
    path is still verified to stay under the root as defense in depth."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ObjectNotFoundError(key)
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._path(key).read_bytes)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._path(key).unlink)
        except FileNotFoundError:
            pass  # idempotent, matching R2


def build_object_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "r2":
        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", settings.r2_account_id),
                ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
                ("R2_BUCKET", settings.r2_bucket),
            )
            if not value
        ]
        if missing:
            raise StorageConfigurationError(
                f"STORAGE_BACKEND=r2 but {', '.join(missing)} not set"
            )
        return R2ObjectStorage(settings)
    return LocalObjectStorage(settings.local_storage_dir)
