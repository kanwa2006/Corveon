"""Chat CRUD endpoints (docs/API.md — Chats).

Every query is scoped by the authenticated user's id — both by the
repository (app guard) and by Postgres RLS via ``RlsDbDep`` (ADR-0013). A
chat that exists but belongs to another user returns 404, not 403, so a
crafted id can never distinguish "not found" from "not yours" (CLAUDE.md §8).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import AfterValidator

from app.api.deps import ArqDep, CurrentUserDep, RlsDbDep
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.chat import ChatCreateRequest, ChatPublic, ChatUpdateRequest
from app.core.validation import reject_nul_bytes
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.document_repository import DocumentRepository

router = APIRouter(prefix="/chats", tags=["chats"])

_DEFAULT_TITLE = "New chat"


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ChatPublic)
async def create_chat(
    payload: ChatCreateRequest, db: RlsDbDep, current_user: CurrentUserDep
) -> ChatPublic:
    repo = ChatRepository(db)
    chat = await repo.create(
        user_id=current_user.id,
        org_id=current_user.org_id,
        title=payload.title or _DEFAULT_TITLE,
    )
    await db.commit()
    return ChatPublic.model_validate(chat)


@router.get("", response_model=list[ChatPublic])
async def list_chats(
    db: RlsDbDep,
    current_user: CurrentUserDep,
    search: Annotated[str | None, Query(), AfterValidator(reject_nul_bytes)] = None,
    pinned: bool | None = Query(default=None),
    archived: bool | None = Query(default=None),
) -> list[ChatPublic]:
    repo = ChatRepository(db)
    chats = await repo.list_for_user(
        current_user.id, search=search, pinned=pinned, archived=archived
    )
    return [ChatPublic.model_validate(chat) for chat in chats]


@router.get("/{chat_id}", response_model=ChatPublic)
async def get_chat(chat_id: uuid.UUID, db: RlsDbDep, current_user: CurrentUserDep) -> ChatPublic:
    repo = ChatRepository(db)
    chat = await get_owned_chat_or_404(repo, chat_id, current_user.id)
    return ChatPublic.model_validate(chat)


@router.patch("/{chat_id}", response_model=ChatPublic)
async def update_chat(
    chat_id: uuid.UUID,
    payload: ChatUpdateRequest,
    db: RlsDbDep,
    current_user: CurrentUserDep,
) -> ChatPublic:
    repo = ChatRepository(db)
    chat = await get_owned_chat_or_404(repo, chat_id, current_user.id)
    chat = await repo.update(
        chat,
        title=payload.title,
        is_pinned=payload.is_pinned,
        is_archived=payload.is_archived,
    )
    await db.commit()
    return ChatPublic.model_validate(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: uuid.UUID,
    request: Request,
    db: RlsDbDep,
    current_user: CurrentUserDep,
    arq: ArqDep,
) -> None:
    # Hard-deletes the chat row (messages/documents/document_chunks/
    # chunk_embeddings cascade at the DB level via ON DELETE CASCADE). The
    # corresponding object-storage blobs don't live in Postgres, so they
    # can't cascade with the row delete — collect their keys first and clean
    # them up in a fire-and-forget ARQ job after the chat is gone (CORVEON
    # blueprint §23.6), rather than blocking this request on N storage
    # deletes. One audit-log entry records the action, not the content.
    repo = ChatRepository(db)
    chat = await get_owned_chat_or_404(repo, chat_id, current_user.id)

    documents = await DocumentRepository(db).list_for_chat(chat_id)
    storage_keys = [document.storage_key for document in documents]

    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="chat.delete",
        entity_type="chat",
        entity_id=chat.id,
        ip=request.client.host if request.client else None,
        metadata={"document_count": len(storage_keys)},
    )
    await repo.delete(chat)
    await db.commit()

    if storage_keys:
        await arq.enqueue_job("delete_storage_objects", storage_keys=storage_keys)
