"""Vector-store selection (ADR-0022) — config-gated, mirroring
``build_provider_registry`` (ADR-0006): the active backend is chosen once from
settings, and business logic never sees which one it got."""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.data.models.chunk import EMBEDDING_DIM
from app.data.vectorstore.base import VectorStore
from app.data.vectorstore.pgvector_store import PgvectorStore
from app.data.vectorstore.qdrant_store import QdrantStore


@lru_cache(maxsize=1)
def get_qdrant_client(url: str, api_key: str | None) -> AsyncQdrantClient:
    """Process-wide cached client (mirrors ``get_embedding_model``) — Qdrant
    is a long-lived HTTP client, not something to reconnect per request."""
    return AsyncQdrantClient(url=url, api_key=api_key)


def build_vector_store(settings: Settings, session: AsyncSession) -> VectorStore:
    """``session`` is only used by the pgvector backend (embeddings live in
    the same transaction as everything else); the Qdrant backend ignores it —
    its client is a separate, cached, long-lived connection."""
    if settings.VECTOR_STORE == "qdrant":
        if settings.QDRANT_URL is None:
            # Unreachable in practice — Settings' model_validator already
            # rejects VECTOR_STORE=qdrant without QDRANT_URL at startup —
            # but narrows the type for the client constructor below.
            raise ValueError("QDRANT_URL is required when VECTOR_STORE=qdrant.")
        client = get_qdrant_client(settings.QDRANT_URL, settings.QDRANT_API_KEY)
        return QdrantStore(client=client, dimension=EMBEDDING_DIM)
    return PgvectorStore(session)
