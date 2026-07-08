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
