"""Chunk + embedding repository. Every similarity query filters by both
chat_id and model_id (ADR-0008) — never mixes vectors across chats or across
embedding-model versions."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.chunk import ChunkEmbedding, DocumentChunk
from app.data.models.document import Document
from app.ingestion.chunking import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create_chunks(
        self, *, chat_id: uuid.UUID, document_id: uuid.UUID, chunks: list[Chunk]
    ) -> list[DocumentChunk]:
        rows = [
            DocumentChunk(
                document_id=document_id,
                chat_id=chat_id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                token_count=chunk.token_count,
            )
            for chunk in chunks
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def bulk_create_embeddings(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        chunk_vectors: list[tuple[uuid.UUID, list[float]]],
    ) -> None:
        rows = [
            ChunkEmbedding(chunk_id=chunk_id, chat_id=chat_id, embedding=vector, model_id=model_id)
            for chunk_id, vector in chunk_vectors
        ]
        self._session.add_all(rows)
        await self._session.flush()

    async def similarity_search(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[tuple[DocumentChunk, Document, float]]:
        """Returns (chunk, parent document, cosine distance) ordered by
        distance ascending (most similar first). Distance is in [0, 2];
        callers render similarity as ``1 - distance`` for display."""
        distance = ChunkEmbedding.embedding.cosine_distance(query_vector)
        stmt = (
            select(DocumentChunk, Document, distance.label("distance"))
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(ChunkEmbedding.chat_id == chat_id, ChunkEmbedding.model_id == model_id)
            .order_by(distance)
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        return [(chunk, document, dist) for chunk, document, dist in result.all()]

    async def has_ready_chunks(self, *, chat_id: uuid.UUID, model_id: str) -> bool:
        """Cheap existence check the orchestrator uses to decide whether RAG
        retrieval has anything to retrieve for this chat (CLAUDE.md §3: no
        always-on retrieval — only retrieve when it could help)."""
        stmt = (
            select(ChunkEmbedding.id)
            .where(ChunkEmbedding.chat_id == chat_id, ChunkEmbedding.model_id == model_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
