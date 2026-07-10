"""Chat request/response schemas (docs/API.md — Chats)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.validation import reject_nul_bytes


class ChatCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)

    _reject_nul_bytes = field_validator("title")(reject_nul_bytes)


class ChatUpdateRequest(BaseModel):
    """PATCH semantics — only provided fields are changed."""

    title: str | None = Field(default=None, max_length=200)
    is_pinned: bool | None = None
    is_archived: bool | None = None

    _reject_nul_bytes = field_validator("title")(reject_nul_bytes)


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
