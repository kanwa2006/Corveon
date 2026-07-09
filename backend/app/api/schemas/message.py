"""Message request/response schemas (docs/API.md — Messages/AI)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.data.models.message import MessageRole
from app.export.message_export import ExportFormat


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class MessagePublic(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    role: MessageRole
    content: str
    routing_trace: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DoneEvent(BaseModel):
    """Payload of the SSE ``done`` event — the persisted assistant message."""

    message_id: uuid.UUID
    routing_trace: dict[str, Any] | None


class ExportRequest(BaseModel):
    format: ExportFormat
