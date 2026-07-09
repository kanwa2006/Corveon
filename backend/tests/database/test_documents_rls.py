"""Database tests: Postgres RLS genuinely enforces per-chat isolation on
messages/documents/document_chunks/chunk_embeddings/jobs (migration 0003) —
independent of any application-layer bug. Bypasses the repository entirely
and issues raw SQL directly, same pattern as test_chats_rls.py. Unlike
`chats` (which carries user_id directly), these tables carry chat_id only,
so their RLS policies check ownership via a correlated EXISTS against
chats — this is what's actually being proven here."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.database, pytest.mark.security]

_ZERO_VECTOR_LITERAL = "[" + ",".join(["0"] * 384) + "]"


async def _insert_user(session: AsyncSession, user_id: uuid.UUID, email: str) -> None:
    await session.execute(
        text(
            "INSERT INTO users (id, email, password_hash, role, is_active, created_at) "
            "VALUES (:id, :email, 'x', 'user', true, now())"
        ),
        {"id": user_id, "email": email},
    )


async def _set_rls_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
    )


async def _insert_chat(session: AsyncSession, chat_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
            "VALUES (:id, :uid, 'x', now(), now())"
        ),
        {"id": chat_id, "uid": user_id},
    )


async def _insert_document(
    session: AsyncSession, document_id: uuid.UUID, chat_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO documents "
            "(id, chat_id, filename, mime_type, size_bytes, storage_key, status, "
            "created_at, updated_at) "
            "VALUES (:id, :chat_id, 'x.pdf', 'application/pdf', 1, 'key', 'pending', now(), now())"
        ),
        {"id": document_id, "chat_id": chat_id},
    )


async def _insert_chunk(
    session: AsyncSession, chunk_id: uuid.UUID, document_id: uuid.UUID, chat_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO document_chunks "
            "(id, document_id, chat_id, ordinal, text, token_count, created_at) "
            "VALUES (:id, :document_id, :chat_id, 0, 'x', 1, now())"
        ),
        {"id": chunk_id, "document_id": document_id, "chat_id": chat_id},
    )


async def _insert_embedding(
    session: AsyncSession, embedding_id: uuid.UUID, chunk_id: uuid.UUID, chat_id: uuid.UUID
) -> None:
    # _ZERO_VECTOR_LITERAL is a fixed module-level constant, never external
    # input — pgvector's `vector` literal syntax has no bind-parameter form,
    # so this is the standard way to pass one via SQLAlchemy `text()`.
    insert_sql = (
        "INSERT INTO chunk_embeddings (id, chunk_id, chat_id, embedding, model_id, created_at) "  # noqa: S608
        f"VALUES (:id, :chunk_id, :chat_id, '{_ZERO_VECTOR_LITERAL}'::vector, 'test-model', now())"
    )
    await session.execute(
        text(insert_sql),
        {"id": embedding_id, "chunk_id": chunk_id, "chat_id": chat_id},
    )


@pytest.mark.asyncio
async def test_messages_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker, chat_id, message_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )

    async for session in app.state.db.session():
        await _insert_user(session, owner, "msg-owner@example.com")
        await _insert_user(session, attacker, "msg-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await session.execute(
            text(
                "INSERT INTO messages (id, chat_id, role, content, created_at) "
                "VALUES (:id, :chat_id, 'user', 'secret', now())"
            ),
            {"id": message_id, "chat_id": chat_id},
        )
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM messages WHERE id = :id"), {"id": message_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's message was visible"
        break


@pytest.mark.asyncio
async def test_messages_rls_allows_owner_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, chat_id, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, owner, "msg-owner2@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await session.execute(
            text(
                "INSERT INTO messages (id, chat_id, role, content, created_at) "
                "VALUES (:id, :chat_id, 'user', 'hi', now())"
            ),
            {"id": message_id, "chat_id": chat_id},
        )
        await session.commit()
        await _set_rls_user(session, owner)
        result = await session.execute(
            text("SELECT * FROM messages WHERE id = :id"), {"id": message_id}
        )
        assert len(result.fetchall()) == 1
        break


@pytest.mark.asyncio
async def test_documents_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker, chat_id, document_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )

    async for session in app.state.db.session():
        await _insert_user(session, owner, "doc-owner@example.com")
        await _insert_user(session, attacker, "doc-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await _insert_document(session, document_id, chat_id)
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": document_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's document was visible"
        break


@pytest.mark.asyncio
async def test_documents_rls_with_check_blocks_cross_chat_insert(app) -> None:  # type: ignore[no-untyped-def]
    """An attacker who knows a victim's chat_id cannot insert a document
    row scoped to it, even though they have a valid, RLS-scoped session."""
    owner, attacker, victim_chat_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, owner, "doc-check-owner@example.com")
        await _insert_user(session, attacker, "doc-check-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, victim_chat_id, owner)
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, attacker)
        with pytest.raises(Exception, match=r"row-level security|new row violates"):
            await _insert_document(session, uuid.uuid4(), victim_chat_id)
            await session.commit()
        break


@pytest.mark.asyncio
async def test_document_chunks_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker, chat_id, document_id, chunk_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )

    async for session in app.state.db.session():
        await _insert_user(session, owner, "chunk-owner@example.com")
        await _insert_user(session, attacker, "chunk-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await _insert_document(session, document_id, chat_id)
        await _insert_chunk(session, chunk_id, document_id, chat_id)
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM document_chunks WHERE id = :id"), {"id": chunk_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's chunk was visible"
        break


@pytest.mark.asyncio
async def test_chunk_embeddings_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker, chat_id, document_id, chunk_id, embedding_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )

    async for session in app.state.db.session():
        await _insert_user(session, owner, "emb-owner@example.com")
        await _insert_user(session, attacker, "emb-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await _insert_document(session, document_id, chat_id)
        await _insert_chunk(session, chunk_id, document_id, chat_id)
        await _insert_embedding(session, embedding_id, chunk_id, chat_id)
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM chunk_embeddings WHERE id = :id"), {"id": embedding_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's embedding was visible"
        break


@pytest.mark.asyncio
async def test_jobs_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker, chat_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, owner, "job-owner@example.com")
        await _insert_user(session, attacker, "job-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await session.execute(
            text(
                "INSERT INTO jobs (id, chat_id, type, status, created_at, updated_at) "
                "VALUES (:id, :chat_id, 'ingest', 'queued', now(), now())"
            ),
            {"id": job_id, "chat_id": chat_id},
        )
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, attacker)
        result = await session.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id})
        assert result.fetchall() == [], "RLS FAILED: another user's job was visible"
        break


@pytest.mark.asyncio
async def test_rls_default_denies_when_guc_unset_on_documents(app) -> None:  # type: ignore[no-untyped-def]
    """No set_config() call at all must fail closed here too, not just on
    chats — same nullif() guard, generated by the same _rls_policy_sql()
    template for all five tables in migration 0003 (checked once here as a
    representative table; the other four share the identical mechanism)."""
    owner, chat_id, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, owner, "unset-guc@example.com")
        await session.commit()
        await _set_rls_user(session, owner)
        await _insert_chat(session, chat_id, owner)
        await _insert_document(session, document_id, chat_id)
        await session.commit()
        break

    async for session in app.state.db.session():
        # GUC never set in this session at all.
        documents = await session.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": document_id}
        )
        assert documents.fetchall() == []
        break
