"""Read-replica plumbing tests (ADR-0023). No second physical Postgres
instance is available in CI, so the "replica" here points at the same
DATABASE_URL as the primary — this proves the plumbing (a genuinely separate
engine + session factory is built, disposed, and RLS re-applied correctly on
it) without asserting anything about real streaming-replication behavior,
which is outside application code's control."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.data.base import Database
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.database, pytest.mark.security]


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


@pytest.mark.asyncio
async def test_database_without_a_replica_configured_falls_back_to_primary() -> None:
    settings = get_settings()
    assert settings.DATABASE_READ_REPLICA_URL is None

    db = Database(settings)
    try:
        assert db.has_read_replica is False
        assert await db.ping_replica() is True
        async for session in db.replica_session():
            await session.execute(text("SELECT 1"))
            break
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_database_with_a_replica_configured_builds_a_second_engine() -> None:
    settings = get_settings().model_copy(
        update={"DATABASE_READ_REPLICA_URL": get_settings().DATABASE_URL}
    )

    db = Database(settings)
    try:
        assert db.has_read_replica is True
        assert await db.ping() is True
        assert await db.ping_replica() is True
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_rls_guc_is_not_shared_between_primary_and_replica_sessions() -> None:
    """The RLS GUC is transaction-local session state, never replicated
    between physical connections (ADR-0013, ADR-0023) — a replica session
    that skips its own set_rls_user call must fail closed, exactly like a
    fresh primary session would (test_rls_default_denies_when_guc_unset)."""
    settings = get_settings().model_copy(
        update={"DATABASE_READ_REPLICA_URL": get_settings().DATABASE_URL}
    )
    db = Database(settings)
    try:
        user_a, chat_a = uuid.uuid4(), uuid.uuid4()

        async for session in db.session():
            await _insert_user(session, user_a, "replica-rls@example.com")
            await _set_rls_user(session, user_a)
            await session.execute(
                text(
                    "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
                    "VALUES (:id, :uid, 'Owned', now(), now())"
                ),
                {"id": chat_a, "uid": user_a},
            )
            await session.commit()
            break

        # A replica session with the GUC never set in this scope reads zero
        # rows, same fail-closed behavior as an unset primary session.
        async for session in db.replica_session():
            result = await session.execute(
                text("SELECT * FROM chats WHERE id = :id"), {"id": chat_a}
            )
            assert result.fetchall() == []
            break

        # Re-applying set_rls_user on the replica session (exactly what
        # get_rls_scoped_read_db does per request) makes the row visible.
        async for session in db.replica_session():
            await _set_rls_user(session, user_a)
            result = await session.execute(
                text("SELECT * FROM chats WHERE id = :id"), {"id": chat_a}
            )
            assert len(result.fetchall()) == 1
            break
    finally:
        await db.dispose()
