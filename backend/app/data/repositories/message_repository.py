"""Message repository — every query scoped by chat_id (docs/ARCHITECTURE.md §5)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.message import Message, MessageRole


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_chat(self, chat_id: uuid.UUID) -> list[Message]:
        result = await self._session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        chat_id: uuid.UUID,
        role: MessageRole,
        content: str,
        routing_trace: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(chat_id=chat_id, role=role, content=content, routing_trace=routing_trace)
        self._session.add(message)
        await self._session.flush()
        return message
