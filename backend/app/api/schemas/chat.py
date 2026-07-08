"""Chat request/response schemas (docs/API.md — Chats)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ChatUpdateRequest(BaseModel):
    """PATCH semantics — only provided fields are changed."""

    title: str | None = Field(default=None, max_length=200)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class ChatPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    org_id: uuid.UUID | None
    title: str
    is_pinned: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
