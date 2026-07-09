"""Message — one chat turn (docs/ARCHITECTURE.md §4). Content-bearing: always
scoped by chat_id (the isolation anchor, §5). Immutable once written — no
TimestampMixin/updated_at."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_chat_id_created_at", "chat_id", "created_at"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(
            MessageRole,
            name="message_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Populated only on assistant messages that ran the orchestrator (docs/API.md
    # "Every response that runs the orchestrator carries a routing_trace object").
    routing_trace: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
