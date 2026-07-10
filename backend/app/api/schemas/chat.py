"""Chat request/response schemas (docs/API.md — Chats)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChatCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ChatUpdateRequest(BaseModel):
    """PATCH semantics — only provided fields are changed."""

    title: str | None = Field(default=None, max_length=200)
    is_pinned: bool | None = None
    is_archived: bool | None = None

    @field_validator("title")
    @classmethod
    def _reject_nul_bytes(cls, value: str | None) -> str | None:
        # Postgres text columns reject an embedded NUL byte at the wire
        # level (asyncpg raises CharacterNotInRepertoireError) — a Python
        # str otherwise allows it freely, so this must be caught here to
        # surface as a 422, not an uncaught 500 from the DB driver.
        if value is not None and "\x00" in value:
            raise ValueError("title must not contain NUL bytes.")
        return value


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
