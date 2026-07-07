"""Chat — the per-user tenancy anchor for content (docs/ARCHITECTURE.md §4, §5).

Unlike users/organizations, a chat IS the isolation boundary that every other
content table (messages, documents, ...) will reference via chat_id once
those land. For the chats table itself, the isolation key is ownership
(user_id) — enforced app-side, by Postgres RLS (migration 0002), and by the
repository layer refusing any query lacking a user_id predicate.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, false
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Chat(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(nullable=False)
    is_pinned: Mapped[bool] = mapped_column(nullable=False, server_default=false())
    is_archived: Mapped[bool] = mapped_column(nullable=False, server_default=false())
