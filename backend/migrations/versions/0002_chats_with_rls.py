"""chats table with row-level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY_NAME = "chats_user_isolation"


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
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
            ["user_id"], ["users.id"], name=op.f("fk_chats_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_chats_org_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chats")),
    )
    op.create_index(op.f("ix_chats_user_id"), "chats", ["user_id"])

    # Row-Level Security (docs/ARCHITECTURE.md §5) — defense in depth alongside
    # the app guard and the repository invariant. FORCE is required because
    # the app's own DB role owns this table, and Postgres exempts table owners
    # from RLS by default unless forced.
    op.execute("ALTER TABLE chats ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chats FORCE ROW LEVEL SECURITY")
    # nullif(..., '') guards against Postgres resetting an unset custom GUC to
    # '' (not NULL) once its LOCAL scope ends — without it, a query that (by
    # bug or accident) never called set_config() would raise a raw
    # "invalid input syntax for type uuid" error instead of gracefully
    # denying access. current_setting(..., true) already returns NULL when
    # the GUC was never touched in this session at all; nullif() covers the
    # "touched previously in this pooled connection, now reset" case too.
    op.execute(
        f"""
        CREATE POLICY {_POLICY_NAME} ON chats
        USING (
            user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
        )
        WITH CHECK (
            user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON chats")
    op.drop_index(op.f("ix_chats_user_id"), table_name="chats")
    op.drop_table("chats")
