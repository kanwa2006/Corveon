"""Database tests: Postgres RLS genuinely enforces per-chat isolation on
medications/medication_findings (migration 0006) — independent of any
application-layer bug. Bypasses the repository entirely and issues raw SQL
directly, same pattern as test_evidence_rls.py.

drug_data_snapshots/drug_interactions are deliberately not covered here —
they are shared reference data (not chat-scoped), see
app/data/models/medication.py."""

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


async def _insert_chat(session: AsyncSession, chat_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO chats (id, user_id, title, created_at, updated_at) "
            "VALUES (:id, :uid, 'x', now(), now())"
        ),
        {"id": chat_id, "uid": user_id},
    )


async def _insert_medication(
    session: AsyncSession, medication_id: uuid.UUID, chat_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO medications (id, chat_id, raw_text, name, created_at) "
            "VALUES (:id, :chat_id, 'secret drug 500mg', 'secret drug', now())"
        ),
        {"id": medication_id, "chat_id": chat_id},
    )


async def _insert_finding(
    session: AsyncSession, finding_id: uuid.UUID, chat_id: uuid.UUID, medication_a_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO medication_findings "
            "(id, chat_id, medication_a_id, type, severity, source, rule_id, explanation, "
            "provenance, created_at) "
            "VALUES (:id, :chat_id, :medication_a_id, 'interaction', 'major', 'ddinter', "
            "'rule-1', 'secret explanation', '{}'::jsonb, now())"
        ),
        {"id": finding_id, "chat_id": chat_id, "medication_a_id": medication_a_id},
    )


async def _seed_owner_chain(
    session: AsyncSession, *, owner: uuid.UUID, email: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Creates user -> chat -> medication -> finding, all owned by
    ``owner``, RLS-scoped throughout. Returns (chat_id, medication_id,
    finding_id)."""
    chat_id, medication_id, finding_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _insert_user(session, owner, email)
    await session.commit()
    await _set_rls_user(session, owner)
    await _insert_chat(session, chat_id, owner)
    await _insert_medication(session, medication_id, chat_id)
    await _insert_finding(session, finding_id, chat_id, medication_id)
    await session.commit()
    return chat_id, medication_id, finding_id


@pytest.mark.asyncio
async def test_medications_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        _, medication_id, _ = await _seed_owner_chain(
            session, owner=owner, email="med-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "med-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM medications WHERE id = :id"), {"id": medication_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's medication was visible"
        break


@pytest.mark.asyncio
async def test_medications_rls_allows_owner_select(app) -> None:  # type: ignore[no-untyped-def]
    owner = uuid.uuid4()

    async for session in app.state.db.session():
        _, medication_id, _ = await _seed_owner_chain(
            session, owner=owner, email="med-owner2@example.com"
        )
        await _set_rls_user(session, owner)
        result = await session.execute(
            text("SELECT * FROM medications WHERE id = :id"), {"id": medication_id}
        )
        assert len(result.fetchall()) == 1
        break


@pytest.mark.asyncio
async def test_medications_rls_with_check_blocks_cross_chat_insert(app) -> None:  # type: ignore[no-untyped-def]
    """An attacker who knows a victim's chat_id cannot insert a medication
    row scoped to it, even with a valid RLS-scoped session."""
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        victim_chat_id, _, _ = await _seed_owner_chain(
            session, owner=owner, email="med-check-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "med-check-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        with pytest.raises(Exception, match=r"row-level security|new row violates"):
            await _insert_medication(session, uuid.uuid4(), victim_chat_id)
            await session.commit()
        break


@pytest.mark.asyncio
async def test_medication_findings_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        _, _, finding_id = await _seed_owner_chain(
            session, owner=owner, email="finding-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "finding-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM medication_findings WHERE id = :id"), {"id": finding_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's finding was visible"
        break


@pytest.mark.asyncio
async def test_medication_findings_rls_allows_owner_select(app) -> None:  # type: ignore[no-untyped-def]
    owner = uuid.uuid4()

    async for session in app.state.db.session():
        _, _, finding_id = await _seed_owner_chain(
            session, owner=owner, email="finding-owner2@example.com"
        )
        await _set_rls_user(session, owner)
        result = await session.execute(
            text("SELECT * FROM medication_findings WHERE id = :id"), {"id": finding_id}
        )
        assert len(result.fetchall()) == 1
        break
