"""User repository — the only place that queries the users table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER,
        org_id: uuid.UUID | None = None,
    ) -> User:
        user = User(email=email, password_hash=password_hash, role=role, org_id=org_id)
        self._session.add(user)
        await self._session.flush()
        return user
