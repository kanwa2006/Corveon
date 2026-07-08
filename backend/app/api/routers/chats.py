"""Chat CRUD endpoints (docs/API.md — Chats).

Every query is scoped by the authenticated user's id — both by the
repository (app guard) and by Postgres RLS via ``RlsDbDep`` (ADR-0013). A
chat that exists but belongs to another user returns 404, not 403, so a
crafted id can never distinguish "not found" from "not yours" (CLAUDE.md §8).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserDep, RlsDbDep
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.chat import ChatCreateRequest, ChatPublic, ChatUpdateRequest
from app.data.repositories.chat_repository import ChatRepository

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
    search: str | None = Query(default=None),
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
async def delete_chat(chat_id: uuid.UUID, db: RlsDbDep, current_user: CurrentUserDep) -> None:
    # Hard-deletes the chat row directly. §23.6's ARQ-cascade delete job
    # applies once there is content (messages, documents, embeddings, R2
    # objects) to cascade to — none of that exists yet at this point in the
    # roadmap, so there is nothing for an async job to do beyond this.
    repo = ChatRepository(db)
    chat = await get_owned_chat_or_404(repo, chat_id, current_user.id)
    await repo.delete(chat)
    await db.commit()
