"""Auth endpoints (docs/API.md — Auth)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, DbDep, RedisDep, SettingsDep
from app.api.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.token_denylist import is_revoked, revoke
from app.data.repositories.user_repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserPublic)
async def me(current_user: CurrentUserDep) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserPublic)
async def register(payload: RegisterRequest, db: DbDep, settings: SettingsDep) -> UserPublic:
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email) is not None:
        raise ConflictError("An account with this email already exists.")

    user = await repo.create(
        email=payload.email,
        password_hash=hash_password(payload.password, settings),
    )
    await db.commit()
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbDep, settings: SettingsDep) -> TokenResponse:
    repo = UserRepository(db)
    user = await repo.get_by_email(payload.email)
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash, settings)
    ):
        raise UnauthorizedError("Incorrect email or password.")

    return TokenResponse(
        access=create_access_token(str(user.id), settings, role=user.role.value),
        refresh=create_refresh_token(str(user.id), settings),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    payload: RefreshRequest, db: DbDep, redis: RedisDep, settings: SettingsDep
) -> AccessTokenResponse:
    try:
        claims = decode_token(payload.refresh_token, TokenType.REFRESH, settings)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired refresh token.") from exc

    jti = claims.get("jti")
    if jti and await is_revoked(redis, jti):
        raise UnauthorizedError("Refresh token has been revoked.")

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed refresh token.") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")

    return AccessTokenResponse(
        access=create_access_token(str(user.id), settings, role=user.role.value)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    redis: RedisDep,
    settings: SettingsDep,
    _current_user: CurrentUserDep,
) -> None:
    if not payload.refresh_token:
        return

    try:
        claims = decode_token(payload.refresh_token, TokenType.REFRESH, settings)
    except InvalidTokenError:
        return  # already invalid — nothing to revoke; logout stays idempotent

    jti = claims.get("jti")
    exp = claims.get("exp")
    if jti and exp:
        await revoke(redis, jti, datetime.fromtimestamp(exp, tz=UTC))
