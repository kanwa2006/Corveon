"""Vector-store contract (ADR-0001, ADR-0022). ``ChunkRepository`` depends only
on this module's type — never a concrete backend name (CLAUDE.md §5's "business
logic never names a concrete AI provider" pattern, applied to vector storage).

Every method is keyed by ``(chat_id, model_id)`` and operates on chunk UUIDs and
raw vectors only — never ORM-joined rows, since a vector backend cannot return a
joined ``Document`` row. Chunk text always lives in Postgres regardless of which
backend stores the embeddings; callers join back to it themselves."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class VectorStore(ABC):
    name: str

    @abstractmethod
    async def upsert(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        chunk_vectors: list[tuple[uuid.UUID, list[float]]],
    ) -> None:
        """Writes (or overwrites) one embedding per ``(chunk_id, vector)`` pair."""
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        *,
        chat_id: uuid.UUID,
        model_id: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[tuple[uuid.UUID, float]]:
        """Returns ``(chunk_id, cosine_distance)`` pairs ordered by distance
        ascending (most similar first), filtered to this chat and model only
        (ADR-0008 — never mixes vectors across chats or embedding-model
        versions)."""
        raise NotImplementedError

    @abstractmethod
    async def has_vectors(self, *, chat_id: uuid.UUID, model_id: str) -> bool:
        """Cheap existence check — has this chat got anything indexed under
        this model yet?"""
        raise NotImplementedError

    @abstractmethod
    async def embedded_chunk_ids(self, *, chat_id: uuid.UUID, model_id: str) -> set[uuid.UUID]:
        """All chunk_ids that already have a vector for this chat + model —
        used to compute the reindex job's remaining work queue."""
        raise NotImplementedError
