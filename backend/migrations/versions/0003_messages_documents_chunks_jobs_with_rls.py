"""messages, documents, document_chunks, chunk_embeddings, jobs — with RLS

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_message_role = postgresql.ENUM("user", "assistant", name="message_role", create_type=False)
_document_status = postgresql.ENUM(
    "pending", "processing", "ready", "failed", name="document_status", create_type=False
)
_job_type = postgresql.ENUM("ingest", name="job_type", create_type=False)
_job_status = postgresql.ENUM(
    "queued", "running", "succeeded", "failed", name="job_status", create_type=False
)

_EMBEDDING_DIM = 384

# RLS (docs/ARCHITECTURE.md §5): chat_id is the isolation anchor for content
# tables, but only `chats` carries user_id directly, so every policy here
# checks ownership via a correlated EXISTS against chats — the same
# nullif(...)::uuid guard as chats_user_isolation (ADR-0013), applied per table.
_TABLES_WITH_CHAT_ID_RLS = ("messages", "documents", "document_chunks", "chunk_embeddings", "jobs")


def _rls_policy_sql(table: str) -> str:
    # `table` is always one of the fixed literals in _TABLES_WITH_CHAT_ID_RLS
    # above (never external input), so this is not an injection vector.
    policy_name = f"{table}_chat_isolation"
    sql = f"""
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
    return sql


def upgrade() -> None:
    # The pgvector extension requires superuser privileges to create and is
    # therefore installed at infra-bootstrap time (infra/postgres-init/, CI
    # workflow step), not here — the app's own DB role is deliberately a
    # non-superuser (ADR-0013) and cannot run CREATE EXTENSION.
    _message_role.create(op.get_bind(), checkfirst=True)
    _document_status.create(op.get_bind(), checkfirst=True)
    _job_type.create(op.get_bind(), checkfirst=True)
    _job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("role", _message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("routing_trace", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["chats.id"], name=op.f("fk_messages_chat_id_chats"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_chat_id_created_at", "messages", ["chat_id", "created_at"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("status", _document_status, server_default="pending", nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
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
            ["chat_id"], ["chats.id"], name=op.f("fk_documents_chat_id_chats"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(op.f("ix_documents_chat_id"), "documents", ["chat_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_document_chunks_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_document_chunks_document_id_ordinal"
        ),
    )
    op.create_index("ix_document_chunks_chat_id", "document_chunks", ["chat_id"])

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_chunk_embeddings_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_chunk_embeddings_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk_embeddings")),
        sa.UniqueConstraint("chunk_id", name="uq_chunk_embeddings_chunk_id"),
    )
    op.create_index(
        "ix_chunk_embeddings_chat_id_model_id", "chunk_embeddings", ["chat_id", "model_id"]
    )
    # HNSW index — raw DDL, deliberately not a tracked model Index (ADR-0015).
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_embedding_hnsw ON chunk_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("type", _job_type, nullable=False),
        sa.Column("status", _job_status, server_default="queued", nullable=False),
        sa.Column("progress_stage", sa.String(), nullable=True),
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
            ["chat_id"], ["chats.id"], name=op.f("fk_jobs_chat_id_chats"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_chat_id"), "jobs", ["chat_id"])

    for table in _TABLES_WITH_CHAT_ID_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(_rls_policy_sql(table))


def downgrade() -> None:
    for table in reversed(_TABLES_WITH_CHAT_ID_RLS):
        op.execute(f"DROP POLICY IF EXISTS {table}_chat_isolation ON {table}")

    op.drop_index(op.f("ix_jobs_chat_id"), table_name="jobs")
    op.drop_table("jobs")

    op.execute("DROP INDEX IF EXISTS ix_chunk_embeddings_embedding_hnsw")
    op.drop_index("ix_chunk_embeddings_chat_id_model_id", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")

    op.drop_index("ix_document_chunks_chat_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index(op.f("ix_documents_chat_id"), table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_messages_chat_id_created_at", table_name="messages")
    op.drop_table("messages")

    _job_status.drop(op.get_bind(), checkfirst=True)
    _job_type.drop(op.get_bind(), checkfirst=True)
    _document_status.drop(op.get_bind(), checkfirst=True)
    _message_role.drop(op.get_bind(), checkfirst=True)
    # The vector extension is infra-managed (see upgrade()) — not dropped here.
