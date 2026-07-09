"""Document chunk + embedding (docs/ARCHITECTURE.md §4). ``chat_id`` is
denormalized onto both tables (not just reachable via document_id) so every
retrieval/search query can filter directly on it without a join — the
isolation anchor invariant (§5) applies at the leaf, not just the parent."""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

EMBEDDING_DIM = 384  # must match settings.EMBEDDING_MODEL_ID output (bge-small-en / e5-small)


class DocumentChunk(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_document_chunks_document_id_ordinal"),
        Index("ix_document_chunks_chat_id", "chat_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(nullable=False)


class ChunkEmbedding(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_chunk_embeddings_chunk_id"),
        Index("ix_chunk_embeddings_chat_id_model_id", "chat_id", "model_id"),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    # HNSW index on this column is created via raw DDL in migration 0003, not a
    # tracked model Index (ADR-0015) — deliberately absent from Base.metadata.
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model_id: Mapped[str] = mapped_column(nullable=False)
