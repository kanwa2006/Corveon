"""Document upload + listing endpoints (docs/API.md — Documents/uploads;
docs/SECURITY.md — malicious-upload defenses). Parsing itself never runs in
the request path — it's queued to the ARQ ingestion worker (app/workers/),
so a malformed/hostile PDF can't tie up an API request."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, UploadFile, status

from app.api.deps import ArqDep, CurrentUserDep, RlsDbDep, StorageDep
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.document import DocumentPublic, UploadAcceptedResponse
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.data.models.document import DocumentStatus
from app.data.models.job import JobType
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.document_repository import DocumentRepository
from app.data.repositories.job_repository import JobRepository

router = APIRouter(tags=["documents"])

_ALLOWED_EXTENSION = ".pdf"
_ALLOWED_MIME_TYPES = {"application/pdf"}
_PDF_MAGIC_BYTES = b"%PDF-"
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB — PDF-bomb/abuse defense


@router.post(
    "/chats/{chat_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAcceptedResponse,
)
async def upload_document(
    chat_id: uuid.UUID,
    file: UploadFile,
    db: RlsDbDep,
    current_user: CurrentUserDep,
    storage: StorageDep,
    arq: ArqDep,
) -> UploadAcceptedResponse:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(_ALLOWED_EXTENSION):
        raise ValidationAppError("Only PDF uploads are supported.")
    if file.content_type not in _ALLOWED_MIME_TYPES:
        raise ValidationAppError("Only application/pdf uploads are supported.")

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ValidationAppError(
            f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB upload limit."
        )
    if not data.startswith(_PDF_MAGIC_BYTES):
        raise ValidationAppError("File content does not look like a valid PDF.")

    document_repo = DocumentRepository(db)
    document = await document_repo.create(
        chat_id=chat_id,
        filename=filename,
        mime_type=file.content_type or "application/pdf",
        size_bytes=len(data),
        storage_key=f"{chat_id}/{uuid.uuid4()}.pdf",
    )

    job_repo = JobRepository(db)
    job = await job_repo.create(chat_id=chat_id, type_=JobType.INGEST)

    await storage.put(document.storage_key, data, content_type=document.mime_type)
    await db.commit()

    await arq.enqueue_job(
        "ingest_document",
        job_id=str(job.id),
        document_id=str(document.id),
        chat_id=str(chat_id),
        user_id=str(current_user.id),
    )

    return UploadAcceptedResponse(job_id=job.id)


@router.get("/chats/{chat_id}/documents", response_model=list[DocumentPublic])
async def list_documents(
    chat_id: uuid.UUID, db: RlsDbDep, current_user: CurrentUserDep
) -> list[DocumentPublic]:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)
    document_repo = DocumentRepository(db)
    documents = await document_repo.list_for_chat(chat_id)
    return [DocumentPublic.model_validate(document) for document in documents]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, db: RlsDbDep, current_user: CurrentUserDep, storage: StorageDep
) -> None:
    # Flat resource (no chat_id in the URL) — RLS narrows get_by_id to rows
    # this user's chats own; the explicit ChatRepository recheck below is the
    # app-layer half of the same defense-in-depth (docs/SECURITY.md).
    document_repo = DocumentRepository(db)
    document = await document_repo.get_by_id(document_id)
    if document is None:
        raise NotFoundError("Document not found.")

    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, document.chat_id, current_user.id)

    if document.status == DocumentStatus.PROCESSING:
        # Deleting mid-ingestion would race the worker's own writes to this
        # same row (it holds the ORM object across the whole pipeline rather
        # than re-fetching per stage) — reject rather than risk a silent,
        # order-dependent partial state.
        raise ConflictError("Document is still being processed; try again shortly.")

    await storage.delete(document.storage_key)
    await document_repo.delete(document)
    await db.commit()
