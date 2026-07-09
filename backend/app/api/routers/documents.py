"""Document upload + listing endpoints (docs/API.md — Documents/uploads;
docs/SECURITY.md — malicious-upload defenses). Parsing itself never runs in
the request path — it's queued to the ARQ ingestion worker (app/workers/),
so a malformed/hostile PDF can't tie up an API request."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, status

from app.api.deps import ArqDep, CurrentUserDep, RlsDbDep, StorageDep
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.document import DocumentPublic, UploadAcceptedResponse
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.data.models.document import DocumentStatus
from app.data.models.job import JobType
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.document_repository import DocumentRepository
from app.data.repositories.job_repository import JobRepository

router = APIRouter(tags=["documents"])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB — upload-bomb/abuse defense


@dataclass(frozen=True, slots=True)
class _FormatSpec:
    # The MIME type stored on the Document row and passed to app.ingestion.
    # parsing.parse_document — derived from the file *extension*, not trusted
    # from the client's Content-Type header, since browsers are inconsistent
    # about what they send for less-common types (docs/SECURITY.md: validate
    # at the boundary, don't trust client-supplied metadata).
    mime_type: str
    # Binary file-signature check; None for text formats, which are
    # validated by UTF-8 decodability instead (see upload_document below).
    magic_bytes: tuple[bytes, ...] | None


# Keyed by lowercased file extension — the single source of truth this
# endpoint, app.ingestion.parsing.parse_document, and the ARQ worker all
# agree on. Adding a format means adding one entry here plus one parser
# function, not touching validation logic.
_ALLOWED_FORMATS: dict[str, _FormatSpec] = {
    ".pdf": _FormatSpec("application/pdf", (b"%PDF-",)),
    ".docx": _FormatSpec(_DOCX_MIME, (b"PK\x03\x04",)),
    ".pptx": _FormatSpec(_PPTX_MIME, (b"PK\x03\x04",)),
    ".md": _FormatSpec("text/markdown", None),
    ".markdown": _FormatSpec("text/markdown", None),
    ".png": _FormatSpec("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": _FormatSpec("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": _FormatSpec("image/jpeg", (b"\xff\xd8\xff",)),
}


@router.post(
    "/chats/{chat_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAcceptedResponse,
)
async def upload_document(
    chat_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    db: RlsDbDep,
    current_user: CurrentUserDep,
    storage: StorageDep,
    arq: ArqDep,
) -> UploadAcceptedResponse:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    filename = file.filename or "upload"
    extension = Path(filename).suffix.lower()
    spec = _ALLOWED_FORMATS.get(extension)
    if spec is None:
        supported = ", ".join(sorted(_ALLOWED_FORMATS))
        raise ValidationAppError(f"Unsupported file type {extension!r}. Supported: {supported}.")

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ValidationAppError(
            f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB upload limit."
        )
    if spec.magic_bytes is not None and not data.startswith(spec.magic_bytes):
        raise ValidationAppError("File content does not match its extension.")
    if spec.magic_bytes is None:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationAppError("File is not valid UTF-8 text.") from exc

    document_repo = DocumentRepository(db)
    document = await document_repo.create(
        chat_id=chat_id,
        filename=filename,
        mime_type=spec.mime_type,
        size_bytes=len(data),
        storage_key=f"{chat_id}/{uuid.uuid4()}{extension}",
    )

    job_repo = JobRepository(db)
    job = await job_repo.create(chat_id=chat_id, type_=JobType.INGEST)

    await storage.put(document.storage_key, data, content_type=document.mime_type)
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="document.upload",
        entity_type="document",
        entity_id=document.id,
        ip=request.client.host if request.client else None,
        metadata={"chat_id": str(chat_id), "filename": filename, "mime_type": spec.mime_type},
    )
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
    document_id: uuid.UUID,
    request: Request,
    db: RlsDbDep,
    current_user: CurrentUserDep,
    storage: StorageDep,
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
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="document.delete",
        entity_type="document",
        entity_id=document.id,
        ip=request.client.host if request.client else None,
        metadata={"chat_id": str(document.chat_id), "filename": document.filename},
    )
    await document_repo.delete(document)
    await db.commit()
