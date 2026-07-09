"""Object storage abstraction (docs/ARCHITECTURE.md §1 Data Layer: Cloudflare R2).

``R2Storage`` is used whenever R2 credentials are fully configured; otherwise
``LocalDiskStorage`` is a disclosed dev/test fallback (ADR-0014) — the same
absence-is-normal posture ADR-0006 established for AI providers, applied to
storage. Both implement the same ``ObjectStorage`` protocol so the ingestion
pipeline is identical regardless of which backend is active.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import Config as BotoConfig

from app.core.config import Settings


class ObjectNotFoundError(Exception):
    """Raised when a storage key does not resolve to a stored object."""


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, *, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class R2Storage:
    """S3-compatible client against Cloudflare R2. boto3 is sync; calls are
    wrapped in ``asyncio.to_thread`` to stay async-first (docs/DEVELOPER.md)."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.R2_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
        except self._client.exceptions.NoSuchKey as exc:
            raise ObjectNotFoundError(key) from exc
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)


class LocalDiskStorage:
    """Dev/test fallback when R2 is not configured (ADR-0014). Single-node
    only — not suitable for multi-instance production deployment."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        # Keys are server-generated (uuid-based); reject traversal defensively
        # regardless, since this still touches the filesystem.
        if ".." in Path(key).parts:
            raise ValueError(f"Invalid storage key: {key!r}")
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        del content_type  # local filesystem has no content-type metadata slot
        await asyncio.to_thread(self._path_for(key).write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.exists():
            raise ObjectNotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        with contextlib.suppress(FileNotFoundError):
            await asyncio.to_thread(path.unlink)


def create_object_storage(settings: Settings) -> ObjectStorage:
    if (
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_ENDPOINT
    ):
        return R2Storage(settings)
    return LocalDiskStorage(Path(settings.LOCAL_STORAGE_DIR))
