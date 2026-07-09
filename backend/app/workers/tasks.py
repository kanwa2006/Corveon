"""Ingestion pipeline task (ARQ, ADR-0011): upload → parse → chunk → embed →
index (docs/ARCHITECTURE.md §3). ``run_ingestion`` is a plain async function,
independent of ARQ's ctx-dict calling convention, so it is directly testable;
``ingest_document`` is the thin wrapper the worker process actually registers.

The worker runs in a separate process from the API, so it has no "current
request" to derive RLS identity from. The API passes ``user_id`` through the
job payload alongside ``chat_id`` (both known at enqueue time from the
authenticated request) specifically so the worker can call ``set_rls_user``
itself — RLS applies to this session exactly as it would to a request's,
never bypassed (ADR-0013)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.storage import ObjectNotFoundError, ObjectStorage
from app.core.tracing import get_tracer
from app.data.base import Database
from app.data.models.document import DocumentStatus
from app.data.models.job import JobStatus
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.repositories.document_repository import DocumentRepository
from app.data.repositories.job_repository import JobRepository
from app.data.rls import commit_and_reapply_rls, set_rls_user
from app.ingestion.chunking import chunk_pages
from app.ingestion.embeddings import EmbeddingModel
from app.ingestion.parsing import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedDocumentTypeError,
    parse_document,
)

logger = get_logger(__name__)
tracer = get_tracer(__name__)

_GENERIC_FAILURE_MESSAGE = "Processing failed. Please try uploading the document again."

# Blueprint §12 lists OCR as its own progress stage. Image uploads always go
# through OCR (app.ingestion.parsing.parse_image) — this can be known and
# surfaced upfront. A PDF's OCR fallback is decided per-page, only inside
# parse_document itself; the stage stays "extracting" for PDFs rather than
# claim a distinction the pipeline can't actually see in advance.
_ALWAYS_OCR_MIME_TYPES = frozenset({"image/png", "image/jpeg"})


def _extract_stage_for(mime_type: str) -> str:
    return "ocr" if mime_type in _ALWAYS_OCR_MIME_TYPES else "extracting"


async def run_ingestion(
    *,
    db: Database,
    storage: ObjectStorage,
    embedding_model: EmbeddingModel,
    job_id: uuid.UUID,
    document_id: uuid.UUID,
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    async for session in db.session():
        await set_rls_user(session, user_id)
        job_repo = JobRepository(session)
        document_repo = DocumentRepository(session)
        chunk_repo = ChunkRepository(session)

        job = await job_repo.get_by_id(job_id)
        document = await document_repo.get_by_id_for_chat(document_id, chat_id)
        if job is None or document is None:
            logger.error("ingestion_missing_row", job_id=str(job_id), document_id=str(document_id))
            return

        try:
            with tracer.start_as_current_span("ingestion.validate"):
                await job_repo.update_progress(
                    job, status=JobStatus.RUNNING, progress_stage="validating"
                )
                await document_repo.update_status(document, status=DocumentStatus.PROCESSING)
                await commit_and_reapply_rls(session, user_id)

            with tracer.start_as_current_span("ingestion.extract"):
                await job_repo.update_progress(
                    job, progress_stage=_extract_stage_for(document.mime_type)
                )
                await commit_and_reapply_rls(session, user_id)
                raw_bytes = await storage.get(document.storage_key)
                parsed = await asyncio.to_thread(parse_document, raw_bytes, document.mime_type)

            with tracer.start_as_current_span("ingestion.chunk"):
                await job_repo.update_progress(job, progress_stage="chunking")
                await commit_and_reapply_rls(session, user_id)
                chunks = chunk_pages(parsed.pages)

            with tracer.start_as_current_span("ingestion.embed"):
                await job_repo.update_progress(job, progress_stage="embedding")
                await commit_and_reapply_rls(session, user_id)
                vectors = await asyncio.to_thread(
                    embedding_model.embed_passages, [chunk.text for chunk in chunks]
                )

            with tracer.start_as_current_span("ingestion.index"):
                await job_repo.update_progress(job, progress_stage="indexing")
                chunk_rows = await chunk_repo.bulk_create_chunks(
                    chat_id=chat_id, document_id=document_id, chunks=chunks
                )
                await chunk_repo.bulk_create_embeddings(
                    chat_id=chat_id,
                    model_id=embedding_model.model_id,
                    chunk_vectors=list(zip((row.id for row in chunk_rows), vectors, strict=True)),
                )
                await document_repo.update_status(
                    document, status=DocumentStatus.READY, page_count=parsed.page_count
                )
                await job_repo.update_progress(
                    job, status=JobStatus.SUCCEEDED, progress_stage="complete"
                )
                await session.commit()

            logger.info("ingestion_succeeded", job_id=str(job_id), document_id=str(document_id))

        except (
            DocumentParseError,
            DocumentTooLargeError,
            UnsupportedDocumentTypeError,
            ObjectNotFoundError,
        ) as exc:
            # Expected, user-facing failure modes: bad upload content. The
            # message is safe to surface (no internals/PII) — CLAUDE.md §10
            # forbids silencing errors, not surfacing a clear typed one.
            await _mark_failed(
                session, job_repo, document_repo, job_id, document_id, chat_id, user_id, str(exc)
            )
            logger.warning("ingestion_failed", job_id=str(job_id), error=str(exc))
        except Exception as exc:  # never leave a job/document stuck in "running" (CLAUDE.md §10)
            await _mark_failed(
                session,
                job_repo,
                document_repo,
                job_id,
                document_id,
                chat_id,
                user_id,
                _GENERIC_FAILURE_MESSAGE,
            )
            logger.error(
                "ingestion_unexpected_error", job_id=str(job_id), error=str(exc), exc_info=exc
            )
        break


async def _mark_failed(
    session: AsyncSession,
    job_repo: JobRepository,
    document_repo: DocumentRepository,
    job_id: uuid.UUID,
    document_id: uuid.UUID,
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    error: str,
) -> None:
    await session.rollback()
    # set_config(..., true) is transaction-local; rollback ends that
    # transaction just like commit does, so the RLS GUC must be re-applied
    # before this session can run another query (ADR-0013).
    await set_rls_user(session, user_id)
    job = await job_repo.get_by_id(job_id)
    document = await document_repo.get_by_id_for_chat(document_id, chat_id)
    if job is not None:
        await job_repo.update_progress(
            job, status=JobStatus.FAILED, progress_stage="failed", error=error
        )
    if document is not None:
        await document_repo.update_status(document, status=DocumentStatus.FAILED, error=error)
    await session.commit()


async def ingest_document(
    ctx: dict[str, Any], *, job_id: str, document_id: str, chat_id: str, user_id: str
) -> None:
    """ARQ task wrapper — deserializes string args (ARQ's job payload is
    JSON-serialized) and delegates to run_ingestion using the worker-lifetime
    singletons set up in app/workers/main.py's on_startup."""
    await run_ingestion(
        db=ctx["db"],
        storage=ctx["storage"],
        embedding_model=ctx["embedding_model"],
        job_id=uuid.UUID(job_id),
        document_id=uuid.UUID(document_id),
        chat_id=uuid.UUID(chat_id),
        user_id=uuid.UUID(user_id),
    )


async def delete_storage_objects(ctx: dict[str, Any], *, storage_keys: list[str]) -> None:
    """Cleans up object-storage blobs left behind by a chat deletion
    (CORVEON blueprint §23.6: hard-delete cascades to the corresponding
    storage objects). Runs after the chat's DB rows are already gone — the
    caller passes the storage keys it already had in hand rather than this
    task re-deriving them, since there is nothing left in the DB to query by
    the time it runs. ``storage.delete`` is idempotent (both backends treat
    a missing key as success), so a partially-retried job never errors on
    keys it already cleaned up."""
    storage: ObjectStorage = ctx["storage"]
    for key in storage_keys:
        await storage.delete(key)
    logger.info("chat_storage_cleanup_complete", object_count=len(storage_keys))


async def reindex_chat_chunks(
    ctx: dict[str, Any], *, chat_id: str, user_id: str, model_id: str
) -> None:
    """Re-embeds one chat's chunks under a new embedding model (CORVEON
    blueprint §23.4). Triggered when the deployment's default embedding
    model changes — existing embeddings under the old model_id are left in
    place (never mixed with the new ones in a query, ADR-0008) rather than
    deleted, so retrieval keeps working through the cutover; nothing reads
    them again once every chat has a ready set of embeddings under the new
    model_id. Idempotent and resumable: only chunks still missing an
    embedding under ``model_id`` are processed, so a retried or repeatedly
    scheduled run does no redundant work."""
    embedding_model: EmbeddingModel = ctx["embedding_model"]
    if embedding_model.model_id != model_id:
        # The worker's embedding_model is a process-lifetime singleton
        # loaded from settings.EMBEDDING_MODEL_ID (app/workers/main.py); this
        # task can only ever reindex to that model, not an arbitrary one —
        # catches a caller passing a stale/mismatched model_id early rather
        # than silently writing embeddings tagged with the wrong id.
        raise ValueError(
            f"Worker is loaded with embedding model {embedding_model.model_id!r}, "
            f"cannot reindex to {model_id!r}."
        )

    db: Database = ctx["db"]
    chat_uuid = uuid.UUID(chat_id)
    user_uuid = uuid.UUID(user_id)
    async for session in db.session():
        await set_rls_user(session, user_uuid)
        chunk_repo = ChunkRepository(session)
        chunks = await chunk_repo.list_chunks_missing_embedding(
            chat_id=chat_uuid, model_id=model_id
        )
        if not chunks:
            logger.info("reindex_nothing_to_do", chat_id=chat_id, model_id=model_id)
            return

        vectors = await asyncio.to_thread(
            embedding_model.embed_passages, [chunk.text for chunk in chunks]
        )
        await chunk_repo.bulk_create_embeddings(
            chat_id=chat_uuid,
            model_id=model_id,
            chunk_vectors=list(zip((chunk.id for chunk in chunks), vectors, strict=True)),
        )
        await session.commit()
        logger.info("reindex_complete", chat_id=chat_id, model_id=model_id, chunk_count=len(chunks))
        break
