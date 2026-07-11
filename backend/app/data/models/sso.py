"""Org-scoped SSO configuration (ADR-0025). One row per organization — an
org either has SSO configured or it doesn't; `email_domain` is the routing
key `/auth/sso/start` looks up before a user is authenticated at all, so it
must be globally unique across organizations. `client_secret_encrypted` is
Fernet-encrypted at rest (app/sso/crypto.py) and never returned by the API —
the same write-only posture as a password hash."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrgSsoConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "org_sso_configs"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_org_sso_configs_org_id"),
        UniqueConstraint("email_domain", name="uq_org_sso_configs_email_domain"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Only "oidc" today — a distinct column (rather than assuming) so a
    # future SAML implementation (ADR-0025) is additive, not a migration
    # that repurposes an existing column's meaning.
    provider_type: Mapped[str] = mapped_column(nullable=False, server_default="oidc")
    issuer: Mapped[str] = mapped_column(nullable=False)
    client_id: Mapped[str] = mapped_column(nullable=False)
    client_secret_encrypted: Mapped[str] = mapped_column(nullable=False)
    email_domain: Mapped[str] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=true())
