"""evidence verification engine — evidence_verifications/claims/citations, with RLS

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_verification_status = postgresql.ENUM(
    "pending", "running", "succeeded", "failed", name="verification_status", create_type=False
)
_source_class = postgresql.ENUM(
    "uploaded_document",
    "verified_public",
    "org_trusted",
    "ai_reasoning",
    "conflicting_insufficient",
    name="evidence_source_class",
    create_type=False,
)
_source_name = postgresql.ENUM(
    "pubmed",
    "dailymed",
    "openfda",
    "clinicaltrials",
    "mesh",
    "rxnorm",
    "uploaded_document",
    name="evidence_source_name",
    create_type=False,
)

# RLS (docs/ARCHITECTURE.md §5, same pattern as migration 0003): chat_id is
# the isolation anchor; every policy checks ownership via a correlated
# EXISTS against chats (ADR-0013).
_TABLES_WITH_CHAT_ID_RLS = ("evidence_verifications", "evidence_claims", "evidence_citations")


def _rls_policy_sql(table: str) -> str:
    # `table` is always one of the fixed literals in _TABLES_WITH_CHAT_ID_RLS
    # above (never external input), so this is not an injection vector.
    policy_name = f"{table}_chat_isolation"
    return f"""
        CREATE POLICY {policy_name} ON {table}
        USING (
            EXISTS (
                SELECT 1 FROM chats c
                WHERE c.id = {table}.chat_id
                AND c.user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM chats c
                WHERE c.id = {table}.chat_id
                AND c.user_id = nullif(current_setting('app.current_user_id', true), '')::uuid
            )
        )
        """


def upgrade() -> None:
    _verification_status.create(op.get_bind(), checkfirst=True)
    _source_class.create(op.get_bind(), checkfirst=True)
    _source_name.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "evidence_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("status", _verification_status, server_default="pending", nullable=False),
        sa.Column("error", sa.String(), nullable=True),
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
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_evidence_verifications_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_evidence_verifications_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_verifications")),
    )
    op.create_index(
        op.f("ix_evidence_verifications_chat_id"), "evidence_verifications", ["chat_id"]
    )

    op.create_table(
        "evidence_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("verification_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_class", _source_class, nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("confidence_rationale", sa.Text(), nullable=False),
        sa.Column("flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_evidence_claims_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verification_id"],
            ["evidence_verifications.id"],
            name=op.f("fk_evidence_claims_verification_id_evidence_verifications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_claims")),
    )
    op.create_index(op.f("ix_evidence_claims_chat_id"), "evidence_claims", ["chat_id"])

    op.create_table(
        "evidence_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("source", _source_name, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("identifier", sa.String(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("supports_claim", sa.Boolean(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_evidence_citations_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["evidence_claims.id"],
            name=op.f("fk_evidence_citations_claim_id_evidence_claims"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_citations")),
    )
    op.create_index(op.f("ix_evidence_citations_chat_id"), "evidence_citations", ["chat_id"])

    for table in _TABLES_WITH_CHAT_ID_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(_rls_policy_sql(table))


def downgrade() -> None:
    for table in reversed(_TABLES_WITH_CHAT_ID_RLS):
        op.execute(f"DROP POLICY IF EXISTS {table}_chat_isolation ON {table}")

    op.drop_index(op.f("ix_evidence_citations_chat_id"), table_name="evidence_citations")
    op.drop_table("evidence_citations")

    op.drop_index(op.f("ix_evidence_claims_chat_id"), table_name="evidence_claims")
    op.drop_table("evidence_claims")

    op.drop_index(op.f("ix_evidence_verifications_chat_id"), table_name="evidence_verifications")
    op.drop_table("evidence_verifications")

    _source_name.drop(op.get_bind(), checkfirst=True)
    _source_class.drop(op.get_bind(), checkfirst=True)
    _verification_status.drop(op.get_bind(), checkfirst=True)
