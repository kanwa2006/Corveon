"""Chunk + embedding repository. Every similarity query filters by both
chat_id and model_id (ADR-0008) — never mixes vectors across chats or across
embedding-model versions. Vector operations delegate to an injected
``VectorStore`` (ADR-0022) — pgvector by default, Qdrant when configured;
chunk text always lives in Postgres regardless of which one is active."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.chunk import DocumentChunk
from app.data.models.document import Document
from app.data.vectorstore.base import VectorStore
from app.ingestion.chunking import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession, vector_store: VectorStore) -> None:
        self._session = session
        self._vector_store = vector_store

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
        await self._vector_store.upsert(
            chat_id=chat_id, model_id=model_id, chunk_vectors=chunk_vectors
        )

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
        hits = await self._vector_store.search(
            chat_id=chat_id, model_id=model_id, query_vector=query_vector, top_k=top_k
        )
        if not hits:
            return []
        distance_by_chunk_id = dict(hits)
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(distance_by_chunk_id))
        )
        result = await self._session.execute(stmt)
        rows_by_chunk_id = {chunk.id: (chunk, document) for chunk, document in result.all()}
        # Preserve the vector search's distance ordering — the SQL IN fetch
        # above has no defined order of its own.
        return [
            (*rows_by_chunk_id[chunk_id], distance)
            for chunk_id, distance in hits
            if chunk_id in rows_by_chunk_id
        ]

    async def has_ready_chunks(self, *, chat_id: uuid.UUID, model_id: str) -> bool:
        """Cheap existence check the orchestrator uses to decide whether RAG
        retrieval has anything to retrieve for this chat (CLAUDE.md §3: no
        always-on retrieval — only retrieve when it could help)."""
        return await self._vector_store.has_vectors(chat_id=chat_id, model_id=model_id)

    async def list_chunks_missing_embedding(
        self, *, chat_id: uuid.UUID, model_id: str
    ) -> list[DocumentChunk]:
        """Chunks for this chat with no embedding yet under ``model_id`` —
        the reindex job's work queue when the default embedding model
        changes (blueprint §23.4: never mix vectors from different models in
        one query; reindex rather than mix in place)."""
        embedded_ids = await self._vector_store.embedded_chunk_ids(
            chat_id=chat_id, model_id=model_id
        )
        stmt = select(DocumentChunk).where(DocumentChunk.chat_id == chat_id)
        if embedded_ids:
            stmt = stmt.where(DocumentChunk.id.not_in(embedded_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
