"""Postgres RLS session scoping (docs/ARCHITECTURE.md §5 — defense in depth).

Sets a transaction-local GUC (``app.current_user_id``) that RLS policies
reference via ``current_setting('app.current_user_id', true)``. Uses
``set_config()`` rather than a raw ``SET LOCAL`` string so the value is
safely parameterized (no SQL injection surface) — see migration 0002.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_rls_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def commit_and_reapply_rls(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Commit, then immediately re-apply the RLS GUC.

    ``set_config(..., true)`` is transaction-local — a COMMIT (like a
    ROLLBACK) ends that transaction and silently resets the GUC. Any code
    path that commits more than once on the same RLS-scoped session (a
    multi-stage pipeline, a streaming endpoint that persists a message
    mid-request) must call this instead of a bare ``session.commit()``, or
    every query/write after the first commit fails or is silently filtered by
    RLS instead of erroring loudly (ADR-0013)."""
    await session.commit()
    await set_rls_user(session, user_id)
