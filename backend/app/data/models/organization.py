"""Organization — tenant root (docs/ARCHITECTURE.md §4). Not content-bearing:
exempt from the chat_id isolation invariant that applies to chats/documents/etc."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Organization(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(nullable=False)
    plan: Mapped[str] = mapped_column(nullable=False, server_default="free")
