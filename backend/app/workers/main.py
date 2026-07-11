"""ARQ worker entrypoint (ADR-0011). Run with:

    arq app.workers.main.WorkerSettings

A persistent process alongside the API (docs/ARCHITECTURE.md §8), never
serverless — matching the "no long-lived work off Vercel" posture (ADR-0007)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.storage import create_object_storage
from app.data.base import Database
from app.ingestion.embeddings import get_embedding_model
from app.workers.tasks import (
    delete_storage_objects,
    ingest_document,
    reindex_chat_chunks,
    sync_pinned_snapshots,
)

logger = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings)
    ctx["settings"] = settings
    ctx["db"] = Database(settings)
    ctx["storage"] = create_object_storage(settings)
    ctx["embedding_model"] = get_embedding_model(
        settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE
    )
    logger.info("worker_startup_complete")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["db"].dispose()
    logger.info("worker_shutdown_complete")


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Coroutine[Any, Any, None]]]] = [
        ingest_document,
        delete_storage_objects,
        reindex_chat_chunks,
        sync_pinned_snapshots,
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)
