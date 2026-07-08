"""Audit log — append-only record of sensitive actions (CLAUDE.md §8: "Audit-
log sensitive actions (auth, uploads, exports, admin, evidence/medication
findings)"; docs/ARCHITECTURE.md §10.1). Not a content-bearing table in the
per-chat-isolation sense (§5) — it spans users/chats by design, since it
exists precisely to let an admin see actions *across* the system. Never
updated or deleted once written; ``metadata`` records context about the
action, never the sensitive content itself (e.g. an export logs the message
id, not the exported file's contents)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "audit_log"

    # Nullable: some actions worth auditing (e.g. a failed login with an
    # unrecognized email) have no resolvable actor.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    ip: Mapped[str | None] = mapped_column(nullable=True)
    # Python attribute is `audit_metadata`, not `metadata` — SQLAlchemy's
    # DeclarativeBase reserves that name for the class's own MetaData object.
    # The actual DB column is still named `metadata`, matching the blueprint
    # (docs/ARCHITECTURE.md §10.1: "audit_log(..., metadata JSONB, ...)").
    audit_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
