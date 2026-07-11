"""Unit test for the ARQ worker entrypoint (app/workers/main.py) — this
module is only otherwise exercised by actually running
`arq app.workers.main.WorkerSettings` in production, never in CI."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.storage import LocalDiskStorage, ObjectNotFoundError
from app.workers.main import WorkerSettings, on_shutdown, on_startup
from app.workers.tasks import (
    _extract_stage_for,
    delete_storage_objects,
    ingest_document,
    reindex_chat_chunks,
    sync_pinned_snapshots,
)

pytestmark = pytest.mark.unit


def test_worker_settings_registers_ingest_document() -> None:
    assert WorkerSettings.functions == [
        ingest_document,
        delete_storage_objects,
        reindex_chat_chunks,
        sync_pinned_snapshots,
    ]


def test_worker_settings_has_redis_settings_from_env() -> None:
    assert WorkerSettings.redis_settings is not None


@pytest.mark.asyncio
async def test_on_startup_populates_ctx_with_expected_keys() -> None:
    ctx: dict[str, object] = {}
    await on_startup(ctx)
    try:
        assert {"settings", "db", "storage", "embedding_model"} <= ctx.keys()
    finally:
        await on_shutdown(ctx)


@pytest.mark.asyncio
async def test_delete_storage_objects_removes_every_key(tmp_path: Path) -> None:
    """CORVEON blueprint §23.6: chat deletion's storage cleanup job must
    actually remove the objects it's given, not just the DB rows."""
    storage = LocalDiskStorage(tmp_path)
    await storage.put("a/one.pdf", b"one", content_type="application/pdf")
    await storage.put("a/two.pdf", b"two", content_type="application/pdf")

    await delete_storage_objects({"storage": storage}, storage_keys=["a/one.pdf", "a/two.pdf"])

    with pytest.raises(ObjectNotFoundError):
        await storage.get("a/one.pdf")
    with pytest.raises(ObjectNotFoundError):
        await storage.get("a/two.pdf")


@pytest.mark.asyncio
async def test_delete_storage_objects_is_idempotent_on_missing_keys(tmp_path: Path) -> None:
    storage = LocalDiskStorage(tmp_path)
    await delete_storage_objects({"storage": storage}, storage_keys=["never/existed.pdf"])


@pytest.mark.parametrize("mime_type", ["image/png", "image/jpeg"])
def test_extract_stage_is_ocr_for_image_uploads(mime_type: str) -> None:
    """CORVEON blueprint §12: OCR is its own progress stage — image uploads
    always go through it (app.ingestion.parsing.parse_image), so this is
    knowable upfront rather than only discoverable mid-parse."""
    assert _extract_stage_for(mime_type) == "ocr"


@pytest.mark.parametrize(
    "mime_type",
    [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/markdown",
    ],
)
def test_extract_stage_is_extracting_for_non_image_uploads(mime_type: str) -> None:
    """A PDF's OCR fallback is decided per-page inside parse_document — the
    stage can't claim "ocr" upfront the way it can for a plain image."""
    assert _extract_stage_for(mime_type) == "extracting"
