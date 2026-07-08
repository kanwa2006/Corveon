"""Shared helpers for routers operating on chat-scoped resources. A chat that
exists but belongs to another user returns 404, not 403, so a crafted id can
never distinguish "not found" from "not yours" (CLAUDE.md §8)."""

from __future__ import annotations

import uuid

from app.core.errors import NotFoundError
from app.data.models.chat import Chat
from app.data.repositories.chat_repository import ChatRepository


async def get_owned_chat_or_404(
    repo: ChatRepository, chat_id: uuid.UUID, user_id: uuid.UUID
) -> Chat:
    chat = await repo.get_by_id_for_user(chat_id, user_id)
    if chat is None:
        raise NotFoundError("Chat not found.")
    return chat
