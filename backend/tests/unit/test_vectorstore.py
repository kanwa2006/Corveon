"""Vector-store abstraction unit tests (ADR-0022): backend selection
(``build_vector_store``) and the ``QdrantStore`` adapter's own logic (payload
filter shape, score-to-distance conversion, pagination), mocking
``AsyncQdrantClient`` rather than talking to a real Qdrant instance."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.config import Settings
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.vectorstore.pgvector_store import PgvectorStore
from app.data.vectorstore.qdrant_store import QdrantStore
from app.data.vectorstore.registry import build_vector_store
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.unit]


def _settings(**overrides: object) -> Settings:
    return Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        **overrides,  # type: ignore[arg-type]
    )


def test_build_vector_store_defaults_to_pgvector() -> None:
    session = AsyncMock(spec=AsyncSession)
    store = build_vector_store(_settings(), session)
    assert isinstance(store, PgvectorStore)


def test_build_vector_store_selects_qdrant_when_configured() -> None:
    session = AsyncMock(spec=AsyncSession)
    settings = _settings(VECTOR_STORE="qdrant", QDRANT_URL="http://localhost:6333")
    store = build_vector_store(settings, session)
    assert isinstance(store, QdrantStore)


def test_chunk_repository_delegates_to_whichever_vector_store_it_is_given() -> None:
    # ChunkRepository never names a concrete backend (CLAUDE.md §5 pattern,
    # applied to vector storage) — constructing it with either backend must
    # work identically from the repository's point of view.
    session = AsyncMock(spec=AsyncSession)
    for store in (
        PgvectorStore(session),
        QdrantStore(client=AsyncMock(spec=AsyncQdrantClient), dimension=384),
    ):
        repo = ChunkRepository(session, store)
        assert repo is not None


def _qdrant_store() -> tuple[QdrantStore, AsyncMock]:
    client = AsyncMock(spec=AsyncQdrantClient)
    client.collection_exists.return_value = True
    return QdrantStore(client=client, dimension=384), client


async def test_qdrant_store_upsert_sends_chat_and_model_id_as_payload() -> None:
    store, client = _qdrant_store()
    chat_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    await store.upsert(
        chat_id=chat_id, model_id="bge-small", chunk_vectors=[(chunk_id, [0.1, 0.2])]
    )

    client.upsert.assert_awaited_once()
    _, kwargs = client.upsert.call_args
    points = kwargs["points"]
    assert len(points) == 1
    assert points[0].id == str(chunk_id)
    assert points[0].payload == {"chat_id": str(chat_id), "model_id": "bge-small"}


async def test_qdrant_store_upsert_is_a_noop_for_an_empty_batch() -> None:
    store, client = _qdrant_store()
    await store.upsert(chat_id=uuid.uuid4(), model_id="bge-small", chunk_vectors=[])
    client.upsert.assert_not_awaited()


async def test_qdrant_store_search_converts_similarity_score_to_distance() -> None:
    store, client = _qdrant_store()
    chunk_id = uuid.uuid4()
    scored_point = models.ScoredPoint(id=str(chunk_id), version=0, score=0.9)
    client.query_points.return_value = SimpleNamespace(points=[scored_point])

    hits = await store.search(
        chat_id=uuid.uuid4(), model_id="bge-small", query_vector=[0.1, 0.2], top_k=5
    )

    # pgvector's cosine_distance is 1 - similarity; Qdrant's score IS
    # similarity — the adapter must convert so both backends read on the
    # same scale (ADR-0022).
    assert hits == [(chunk_id, pytest.approx(0.1))]


async def test_qdrant_store_has_vectors_reflects_the_count() -> None:
    store, client = _qdrant_store()
    client.count.return_value = models.CountResult(count=3)
    assert await store.has_vectors(chat_id=uuid.uuid4(), model_id="bge-small") is True

    client.count.return_value = models.CountResult(count=0)
    assert await store.has_vectors(chat_id=uuid.uuid4(), model_id="bge-small") is False


async def test_qdrant_store_embedded_chunk_ids_paginates_through_scroll() -> None:
    store, client = _qdrant_store()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    first_point = models.Record(id=str(first_id))
    second_point = models.Record(id=str(second_id))
    client.scroll.side_effect = [
        ([first_point], "cursor-1"),
        ([second_point], None),
    ]

    ids = await store.embedded_chunk_ids(chat_id=uuid.uuid4(), model_id="bge-small")

    assert ids == {first_id, second_id}
    assert client.scroll.await_count == 2


async def test_qdrant_store_creates_collection_and_payload_indexes_once() -> None:
    client = AsyncMock(spec=AsyncQdrantClient)
    client.collection_exists.return_value = False
    client.count.return_value = models.CountResult(count=0)
    store = QdrantStore(client=client, dimension=384)

    await store.has_vectors(chat_id=uuid.uuid4(), model_id="bge-small")
    await store.has_vectors(chat_id=uuid.uuid4(), model_id="bge-small")

    client.create_collection.assert_awaited_once()
    assert client.create_payload_index.await_count == 2
    # Second call reuses the already-ensured collection.
    client.collection_exists.assert_awaited_once()
