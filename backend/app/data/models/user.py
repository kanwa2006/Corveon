"""User — identity + RBAC role (docs/SECURITY.md: user, org-admin, superadmin).
Not content-bearing: exempt from the chat_id isolation invariant."""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, true
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    USER = "user"
    ORG_ADMIN = "org-admin"
    SUPERADMIN = "superadmin"


class User(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    # NULL for an SSO-only account (ADR-0025) — no local password exists to
    # verify against; login() rejects with a clear message rather than a
    # generic auth failure when this is NULL.
    password_hash: Mapped[str | None] = mapped_column(nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=UserRole.USER.value,
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=true())
