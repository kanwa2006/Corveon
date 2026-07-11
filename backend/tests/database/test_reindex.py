"""Embedding reindex job tests (CORVEON blueprint §23.4: changing the
default embedding model requires a background reindex job rather than
in-place mixing, and a similarity query never mixes vectors from different
model_ids)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import fitz
import pytest
from app.core.config import get_settings
from app.data.models.chunk import ChunkEmbedding
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.rls import set_rls_user
from app.data.vectorstore.registry import build_vector_store
from app.ingestion.embeddings import get_embedding_model
from app.workers.tasks import ingest_document, reindex_chat_chunks
from httpx import AsyncClient
from sqlalchemy import select

pytestmark = [pytest.mark.database]

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


def _make_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Reindex test content about metformin.")
    data: bytes = doc.tobytes()
    doc.close()
    return data


async def _upload_and_ingest(
    client: AsyncClient,
    headers: dict[str, str],
    app,  # type: ignore[no-untyped-def]
) -> tuple[str, str]:
    chat = await client.post("/api/v1/chats", json={"title": "Reindex chat"}, headers=headers)
    chat_id: str = chat.json()["id"]
    user_id: str = (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]

    upload = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    job_id = upload.json()["job_id"]
    document_id = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)).json()[
        0
    ]["id"]

    settings = get_settings()
    embedding_model = get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)
    await ingest_document(
        {
            "db": app.state.db,
            "storage": app.state.storage,
            "embedding_model": embedding_model,
            "settings": settings,
        },
        job_id=job_id,
        document_id=document_id,
        chat_id=chat_id,
        user_id=user_id,
    )
    return chat_id, user_id


@pytest.mark.asyncio
async def test_reindex_rejects_a_model_id_the_worker_is_not_loaded_with(app) -> None:  # type: ignore[no-untyped-def]
    settings = get_settings()
    embedding_model = get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)
    with pytest.raises(ValueError, match="cannot reindex to"):
        await reindex_chat_chunks(
            {"embedding_model": embedding_model, "db": app.state.db, "settings": settings},
            chat_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            model_id="some-other-model-nobody-loaded",
        )


@pytest.mark.asyncio
async def test_reindex_is_a_noop_when_every_chunk_already_has_an_embedding(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    app,  # type: ignore[no-untyped-def]
) -> None:
    headers = await auth_headers("reindex-noop@example.com")
    chat_id, user_id = await _upload_and_ingest(client, headers, app)

    settings = get_settings()
    embedding_model = get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)
    await reindex_chat_chunks(
        {"db": app.state.db, "embedding_model": embedding_model, "settings": settings},
        chat_id=chat_id,
        user_id=user_id,
        model_id=settings.EMBEDDING_MODEL_ID,
    )

    async for session in app.state.db.session():
        await set_rls_user(session, uuid.UUID(user_id))
        chunk_repo = ChunkRepository(session, build_vector_store(settings, session))
        remaining = await chunk_repo.list_chunks_missing_embedding(
            chat_id=uuid.UUID(chat_id), model_id=settings.EMBEDDING_MODEL_ID
        )
        assert remaining == []
        assert await chunk_repo.has_ready_chunks(
            chat_id=uuid.UUID(chat_id), model_id=settings.EMBEDDING_MODEL_ID
        )
        break


@pytest.mark.asyncio
async def test_reindex_embeds_chunks_missing_an_embedding(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    app,  # type: ignore[no-untyped-def]
) -> None:
    """Simulates the model-change scenario directly at the repository level:
    a chunk with no embedding row at all under the current model_id (as if
    the default embedding model had just changed) gets one after reindex."""
    headers = await auth_headers("reindex-fills-gap@example.com")
    chat_id, user_id = await _upload_and_ingest(client, headers, app)

    # Drop the embeddings this chat already has, as if its chunks pre-date a
    # default-embedding-model change and have never been embedded under it.
    async for session in app.state.db.session():
        await set_rls_user(session, uuid.UUID(user_id))
        result = await session.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chat_id == uuid.UUID(chat_id))
        )
        for row in result.scalars().all():
            await session.delete(row)
        await session.commit()
        break

    settings = get_settings()
    embedding_model = get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)
    await reindex_chat_chunks(
        {"db": app.state.db, "embedding_model": embedding_model, "settings": settings},
        chat_id=chat_id,
        user_id=user_id,
        model_id=settings.EMBEDDING_MODEL_ID,
    )

    async for session in app.state.db.session():
        await set_rls_user(session, uuid.UUID(user_id))
        chunk_repo = ChunkRepository(session, build_vector_store(settings, session))
        remaining = await chunk_repo.list_chunks_missing_embedding(
            chat_id=uuid.UUID(chat_id), model_id=settings.EMBEDDING_MODEL_ID
        )
        assert remaining == []
        assert await chunk_repo.has_ready_chunks(
            chat_id=uuid.UUID(chat_id), model_id=settings.EMBEDDING_MODEL_ID
        )
        break
