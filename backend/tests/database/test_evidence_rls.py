"""Database tests: Postgres RLS genuinely enforces per-chat isolation on
evidence_verifications/evidence_claims/evidence_citations (migration 0005) —
independent of any application-layer bug. Bypasses the repository entirely
and issues raw SQL directly, same pattern as test_documents_rls.py."""

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


async def _insert_message(session: AsyncSession, message_id: uuid.UUID, chat_id: uuid.UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO messages (id, chat_id, role, content, created_at) "
            "VALUES (:id, :chat_id, 'user', 'x', now())"
        ),
        {"id": message_id, "chat_id": chat_id},
    )


async def _insert_verification(
    session: AsyncSession, verification_id: uuid.UUID, chat_id: uuid.UUID, message_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO evidence_verifications "
            "(id, chat_id, message_id, status, created_at, updated_at) "
            "VALUES (:id, :chat_id, :message_id, 'pending', now(), now())"
        ),
        {"id": verification_id, "chat_id": chat_id, "message_id": message_id},
    )


async def _insert_claim(
    session: AsyncSession, claim_id: uuid.UUID, chat_id: uuid.UUID, verification_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO evidence_claims "
            "(id, chat_id, verification_id, ordinal, text, source_class, "
            "confidence_score, confidence_rationale, flags, created_at) "
            "VALUES (:id, :chat_id, :verification_id, 0, 'secret claim', 'ai_reasoning', "
            "50, 'because', '[]'::jsonb, now())"
        ),
        {"id": claim_id, "chat_id": chat_id, "verification_id": verification_id},
    )


async def _insert_citation(
    session: AsyncSession, citation_id: uuid.UUID, chat_id: uuid.UUID, claim_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO evidence_citations "
            "(id, chat_id, claim_id, source, title, supports_claim, resolved, created_at) "
            "VALUES (:id, :chat_id, :claim_id, 'pubmed', 'secret title', true, true, now())"
        ),
        {"id": citation_id, "chat_id": chat_id, "claim_id": claim_id},
    )


async def _seed_owner_chain(
    session: AsyncSession, *, owner: uuid.UUID, email: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Creates user -> chat -> message -> verification -> claim -> citation,
    all owned by ``owner``, RLS-scoped throughout. Returns
    (chat_id, message_id, verification_id, claim_id, citation_id)."""
    chat_id, message_id, verification_id, claim_id, citation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    await _insert_user(session, owner, email)
    await session.commit()
    await _set_rls_user(session, owner)
    await _insert_chat(session, chat_id, owner)
    await _insert_message(session, message_id, chat_id)
    await _insert_verification(session, verification_id, chat_id, message_id)
    await _insert_claim(session, claim_id, chat_id, verification_id)
    await _insert_citation(session, citation_id, chat_id, claim_id)
    await session.commit()
    return chat_id, message_id, verification_id, claim_id, citation_id


@pytest.mark.asyncio
async def test_evidence_verifications_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        _, _, verification_id, _, _ = await _seed_owner_chain(
            session, owner=owner, email="ev-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "ev-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM evidence_verifications WHERE id = :id"), {"id": verification_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's verification was visible"
        break


@pytest.mark.asyncio
async def test_evidence_verifications_rls_allows_owner_select(app) -> None:  # type: ignore[no-untyped-def]
    owner = uuid.uuid4()

    async for session in app.state.db.session():
        _, _, verification_id, _, _ = await _seed_owner_chain(
            session, owner=owner, email="ev-owner2@example.com"
        )
        await _set_rls_user(session, owner)
        result = await session.execute(
            text("SELECT * FROM evidence_verifications WHERE id = :id"), {"id": verification_id}
        )
        assert len(result.fetchall()) == 1
        break


@pytest.mark.asyncio
async def test_evidence_claims_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        _, _, _, claim_id, _ = await _seed_owner_chain(
            session, owner=owner, email="claim-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "claim-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM evidence_claims WHERE id = :id"), {"id": claim_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's claim was visible"
        break


@pytest.mark.asyncio
async def test_evidence_claims_rls_with_check_blocks_cross_chat_insert(app) -> None:  # type: ignore[no-untyped-def]
    """An attacker who knows a victim's verification_id/chat_id cannot
    insert a claim row scoped to it, even with a valid RLS-scoped session."""
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        victim_chat_id, _, victim_verification_id, _, _ = await _seed_owner_chain(
            session, owner=owner, email="claim-check-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "claim-check-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        with pytest.raises(Exception, match=r"row-level security|new row violates"):
            await _insert_claim(session, uuid.uuid4(), victim_chat_id, victim_verification_id)
            await session.commit()
        break


@pytest.mark.asyncio
async def test_evidence_citations_rls_blocks_cross_user_select(app) -> None:  # type: ignore[no-untyped-def]
    owner, attacker = uuid.uuid4(), uuid.uuid4()

    async for session in app.state.db.session():
        _, _, _, _, citation_id = await _seed_owner_chain(
            session, owner=owner, email="cite-owner@example.com"
        )
        break

    async for session in app.state.db.session():
        await _insert_user(session, attacker, "cite-attacker@example.com")
        await session.commit()
        await _set_rls_user(session, attacker)
        result = await session.execute(
            text("SELECT * FROM evidence_citations WHERE id = :id"), {"id": citation_id}
        )
        assert result.fetchall() == [], "RLS FAILED: another user's citation was visible"
        break
