"""Chat repository — every query is scoped by user_id (app-guard layer,
docs/ARCHITECTURE.md §5). Postgres RLS (migration 0002) enforces the same
invariant independently, as defense in depth."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.chat import Chat


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> list[Chat]:
        query = select(Chat).where(Chat.user_id == user_id)

        if search:
            query = query.where(Chat.title.ilike(f"%{search}%"))
        if pinned is not None:
            query = query.where(Chat.is_pinned == pinned)
        # Archived chats are hidden from the default list, matching common
        # archive UX (Slack, ChatGPT, ...) — pass archived=true to see them.
        query = query.where(Chat.is_archived == (archived if archived is not None else False))

        query = query.order_by(Chat.is_pinned.desc(), Chat.updated_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_for_user(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> Chat | None:
        result = await self._session.execute(
            select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, *, user_id: uuid.UUID, org_id: uuid.UUID | None, title: str) -> Chat:
        chat = Chat(user_id=user_id, org_id=org_id, title=title)
        self._session.add(chat)
        await self._session.flush()
        return chat

    async def update(
        self,
        chat: Chat,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
        is_archived: bool | None = None,
    ) -> Chat:
        if title is not None:
            chat.title = title
        if is_pinned is not None:
            chat.is_pinned = is_pinned
        if is_archived is not None:
            chat.is_archived = is_archived
        await self._session.flush()
        # updated_at is server-computed (onupdate=now()); UPDATE doesn't
        # populate it via RETURNING the way INSERT does, so the attribute is
        # left expired. Refresh before returning — accessing an expired
        # attribute during (synchronous) Pydantic serialization would
        # otherwise attempt an implicit lazy-load outside any async context.
        await self._session.refresh(chat)
        return chat

    async def delete(self, chat: Chat) -> None:
        await self._session.delete(chat)
