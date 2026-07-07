"""Database tests: Postgres RLS genuinely enforces per-user chat isolation
(ADR-0013) — independent of any application-layer bug. Bypasses the repository
entirely and issues raw SQL directly, proving the DB itself is the backstop."""

from __future__ import annotations

import uuid

import pytest
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
async def test_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    user_a, user_b, chat_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, user_a, "rls-a@example.com")
        await _insert_user(session, user_b, "rls-b@example.com")
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
                "VALUES (:id, :uid, 'A only', now(), now())"
            ),
            {"id": chat_a, "uid": user_a},
        )
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, user_b)
        result = await session.execute(text("SELECT * FROM chats WHERE id = :id"), {"id": chat_a})
        assert result.fetchall() == [], "RLS FAILED: another user's row was visible"
        break


@pytest.mark.asyncio
async def test_rls_allows_owner_select(app) -> None:  # type: ignore[no-untyped-def]
    user_a, chat_a = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, user_a, "rls-owner@example.com")
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
                "VALUES (:id, :uid, 'Owned', now(), now())"
            ),
            {"id": chat_a, "uid": user_a},
        )
        await session.commit()
        # set_config(..., true) is LOCAL to the transaction that just ended
        # at commit() — re-set it for this new transaction before selecting.
        await _set_rls_user(session, user_a)
        result = await session.execute(text("SELECT * FROM chats WHERE id = :id"), {"id": chat_a})
        assert len(result.fetchall()) == 1
        break


@pytest.mark.asyncio
async def test_rls_default_denies_when_guc_unset(app) -> None:  # type: ignore[no-untyped-def]
    """No set_config() call at all (e.g. a hypothetical app-layer bug that
    forgets to scope the session) must fail closed — zero rows, no raw
    Postgres exception (the nullif guard in the policy, ADR-0013)."""
    user_a, chat_a = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, user_a, "rls-unset@example.com")
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
                "VALUES (:id, :uid, 'x', now(), now())"
            ),
            {"id": chat_a, "uid": user_a},
        )
        await session.commit()
        break

    # A fresh session/transaction with the GUC never set in this scope.
    async for session in app.state.db.session():
        result = await session.execute(text("SELECT * FROM chats WHERE id = :id"), {"id": chat_a})
        assert result.fetchall() == []
        break


@pytest.mark.asyncio
async def test_rls_with_check_blocks_cross_user_insert(app) -> None:  # type: ignore[no-untyped-def]
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        await _insert_user(session, user_a, "rls-check-a@example.com")
        await _insert_user(session, user_b, "rls-check-b@example.com")
        await session.commit()
        break

    async for session in app.state.db.session():
        await _set_rls_user(session, user_a)
        with pytest.raises(Exception, match=r"row-level security|new row violates"):
            await session.execute(
                text(
                    "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
                    "VALUES (:id, :uid, 'Malicious', now(), now())"
                ),
                {"id": uuid.uuid4(), "uid": user_b},
            )
            await session.commit()
        break
