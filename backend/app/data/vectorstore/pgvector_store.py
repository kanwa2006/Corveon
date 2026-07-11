"""Default vector-store backend (ADR-0001): embeddings live in the
``chunk_embeddings`` Postgres table alongside everything else, queried via
pgvector's cosine-distance operator and the HNSW index (migration 0003,
ADR-0015)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.chunk import ChunkEmbedding
from app.data.vectorstore.base import VectorStore


class PgvectorStore(VectorStore):
    name = "pgvector"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
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

    async def search(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[tuple[uuid.UUID, float]]:
        distance = ChunkEmbedding.embedding.cosine_distance(query_vector)
        stmt = (
            select(ChunkEmbedding.chunk_id, distance.label("distance"))
            .where(ChunkEmbedding.chat_id == chat_id, ChunkEmbedding.model_id == model_id)
            .order_by(distance)
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        return [(chunk_id, dist) for chunk_id, dist in result.all()]

    async def has_vectors(self, *, chat_id: uuid.UUID, model_id: str) -> bool:
        stmt = (
            select(ChunkEmbedding.id)
            .where(ChunkEmbedding.chat_id == chat_id, ChunkEmbedding.model_id == model_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None

    async def embedded_chunk_ids(self, *, chat_id: uuid.UUID, model_id: str) -> set[uuid.UUID]:
        stmt = select(ChunkEmbedding.chunk_id).where(
            ChunkEmbedding.chat_id == chat_id, ChunkEmbedding.model_id == model_id
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())
