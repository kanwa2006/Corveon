"""Shared FastAPI dependencies: DB session, Redis, settings, current user, RBAC."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.core.token_denylist import is_revoked
from app.data.models.user import User, UserRole
from app.data.repositories.user_repository import UserRepository
from app.data.rls import set_rls_user

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in request.app.state.db.session():
        yield session


async def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")

    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS, settings)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc

    jti = payload.get("jti")
    if jti and await is_revoked(redis, jti):
        raise UnauthorizedError("Token has been revoked.")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed token subject.") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_rls_scoped_db(db: DbDep, user: CurrentUserDep) -> AsyncSession:
    """A DB session with the Postgres RLS GUC set for the current user
    (docs/ARCHITECTURE.md §5, ADR-0013) — defense in depth alongside the app
    guard and the repository invariant. Use for any endpoint touching a
    per-user-isolated table (chats and beyond)."""
    await set_rls_user(db, user.id)
    return db


RlsDbDep = Annotated[AsyncSession, Depends(get_rls_scoped_db)]


def require_role(*allowed_roles: UserRole) -> Callable[[User], User]:
    def _check(user: CurrentUserDep) -> User:
        if user.role not in allowed_roles:
            raise ForbiddenError(
                f"Role {user.role.value!r} is not permitted to perform this action."
            )
        return user

    return _check
