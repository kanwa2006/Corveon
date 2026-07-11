"""Opt-in vector-store backend (ADR-0022): embeddings live in a single Qdrant
collection, ``chat_id``/``model_id`` stored as indexed payload fields and
filtered on every call — the same no-cross-chat/no-cross-model-mixing
invariant as pgvector's ``WHERE`` (ADR-0008), enforced via a payload filter
instead of a SQL predicate."""

from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient, models

from app.data.vectorstore.base import VectorStore

_COLLECTION_NAME = "document_chunks"


class QdrantStore(VectorStore):
    name = "qdrant"

    def __init__(self, *, client: AsyncQdrantClient, dimension: int) -> None:
        self._client = client
        self._dimension = dimension
        self._collection_ready = False

    async def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        if not await self._client.collection_exists(_COLLECTION_NAME):
            await self._client.create_collection(
                collection_name=_COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=self._dimension, distance=models.Distance.COSINE
                ),
            )
            await self._client.create_payload_index(
                _COLLECTION_NAME,
                field_name="chat_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await self._client.create_payload_index(
                _COLLECTION_NAME,
                field_name="model_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        self._collection_ready = True

    @staticmethod
    def _chat_model_filter(chat_id: uuid.UUID, model_id: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(key="chat_id", match=models.MatchValue(value=str(chat_id))),
                models.FieldCondition(key="model_id", match=models.MatchValue(value=model_id)),
            ]
        )

    async def upsert(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        chunk_vectors: list[tuple[uuid.UUID, list[float]]],
    ) -> None:
        await self._ensure_collection()
        points = [
            models.PointStruct(
                id=str(chunk_id),
                vector=vector,
                payload={"chat_id": str(chat_id), "model_id": model_id},
            )
            for chunk_id, vector in chunk_vectors
        ]
        if points:
            await self._client.upsert(collection_name=_COLLECTION_NAME, points=points)

    async def search(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[tuple[uuid.UUID, float]]:
        await self._ensure_collection()
        response = await self._client.query_points(
            collection_name=_COLLECTION_NAME,
            query=query_vector,
            query_filter=self._chat_model_filter(chat_id, model_id),
            limit=top_k,
            with_payload=False,
        )
        # Qdrant's cosine score is similarity (higher = better); pgvector's
        # cosine_distance is 1 - similarity — convert so callers (and the
        # `similarity = 1 - distance` rendering in the search endpoint) see
        # the same scale regardless of backend.
        return [(uuid.UUID(str(point.id)), 1.0 - point.score) for point in response.points]

    async def has_vectors(self, *, chat_id: uuid.UUID, model_id: str) -> bool:
        await self._ensure_collection()
        result = await self._client.count(
            collection_name=_COLLECTION_NAME,
            count_filter=self._chat_model_filter(chat_id, model_id),
        )
        return result.count > 0

    async def embedded_chunk_ids(self, *, chat_id: uuid.UUID, model_id: str) -> set[uuid.UUID]:
        await self._ensure_collection()
        ids: set[uuid.UUID] = set()
        next_offset: str | int | uuid.UUID | None = None
        while True:
            points, next_offset = await self._client.scroll(
                collection_name=_COLLECTION_NAME,
                scroll_filter=self._chat_model_filter(chat_id, model_id),
                with_payload=False,
                with_vectors=False,
                limit=256,
                offset=next_offset,
            )
            ids.update(uuid.UUID(str(point.id)) for point in points)
            if next_offset is None:
                break
        return ids
