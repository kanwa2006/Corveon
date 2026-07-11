"""enterprise sso — org_sso_configs table, nullable users.password_hash

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An SSO-only account (ADR-0025) has no local password to verify
    # against — login() rejects with a clear message rather than a generic
    # auth failure when this is NULL. Every existing/normal user is
    # unaffected: this only widens what's allowed.
    op.alter_column("users", "password_hash", nullable=True)

    op.create_table(
        "org_sso_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", sa.String(), server_default="oidc", nullable=False),
        sa.Column("issuer", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("client_secret_encrypted", sa.String(), nullable=False),
        sa.Column("email_domain", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_org_sso_configs_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_sso_configs")),
        sa.UniqueConstraint("org_id", name="uq_org_sso_configs_org_id"),
        sa.UniqueConstraint("email_domain", name="uq_org_sso_configs_email_domain"),
    )


def downgrade() -> None:
    op.drop_table("org_sso_configs")
    op.alter_column("users", "password_hash", nullable=False)
