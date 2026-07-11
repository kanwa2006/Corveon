"""Auth endpoints (docs/API.md — Auth)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUserDep, DbDep, RedisDep, SettingsDep, SsoHttpTransportDep
from app.api.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    StreamTicketResponse,
    TokenResponse,
    UserPublic,
)
from app.api.schemas.sso import SsoStartRequest, SsoStartResponse
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    create_stream_ticket,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.token_denylist import is_revoked, revoke
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.user_repository import UserRepository
from app.sso.service import handle_sso_callback, start_sso_login

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/me", response_model=UserPublic)
async def me(current_user: CurrentUserDep) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/stream-ticket", response_model=StreamTicketResponse)
async def stream_ticket(
    current_user: CurrentUserDep, settings: SettingsDep
) -> StreamTicketResponse:
    """Mints a very-short-lived, single-purpose credential the browser can
    pass as a query parameter to open an SSE connection directly against the
    backend (ADR-0007) — resolves the bridge ADR-0012 deferred to this
    feature, since native EventSource cannot attach the httpOnly session
    cookie or a custom Authorization header cross-origin."""
    return StreamTicketResponse(ticket=create_stream_ticket(str(current_user.id), settings))


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserPublic)
async def register(
    payload: RegisterRequest, request: Request, db: DbDep, settings: SettingsDep
) -> UserPublic:
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email) is not None:
        raise ConflictError("An account with this email already exists.")

    user = await repo.create(
        email=payload.email,
        password_hash=hash_password(payload.password, settings),
    )
    await AuditLogRepository(db).create(
        actor_id=user.id,
        action="user.register",
        entity_type="user",
        entity_id=user.id,
        ip=_client_ip(request),
    )
    await db.commit()
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, db: DbDep, settings: SettingsDep
) -> TokenResponse:
    repo = UserRepository(db)
    user = await repo.get_by_email(payload.email)
    if user is None or not user.is_active:
        raise UnauthorizedError("Incorrect email or password.")
    if user.password_hash is None:
        # SSO-only account (ADR-0025) — no local password exists to verify
        # against. A distinct message here is deliberate, not a leak: SSO
        # routing is already keyed on email domain, publicly discoverable
        # the same way "sign in with Google" buttons are.
        raise UnauthorizedError("This account signs in via SSO. Use your organization's SSO login.")
    if not verify_password(payload.password, user.password_hash, settings):
        raise UnauthorizedError("Incorrect email or password.")

    await AuditLogRepository(db).create(
        actor_id=user.id,
        action="user.login",
        entity_type="user",
        entity_id=user.id,
        ip=_client_ip(request),
    )
    await db.commit()

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
    request: Request,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    current_user: CurrentUserDep,
) -> None:
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="user.logout",
        entity_type="user",
        entity_id=current_user.id,
        ip=_client_ip(request),
    )
    await db.commit()

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


@router.post("/sso/start", response_model=SsoStartResponse)
async def sso_start(
    payload: SsoStartRequest,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    transport: SsoHttpTransportDep,
) -> SsoStartResponse:
    """Looks up the organization's SSO configuration by the email's domain
    and returns the IdP's authorization URL to redirect to (ADR-0025). Not
    authenticated — the user isn't logged in yet."""
    redirect_url = await start_sso_login(
        session=db, redis=redis, settings=settings, email=payload.email, transport=transport
    )
    return SsoStartResponse(redirect_url=redirect_url)


@router.get("/sso/callback", response_model=TokenResponse)
async def sso_callback(
    code: str,
    state: str,
    request: Request,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    transport: SsoHttpTransportDep,
) -> TokenResponse:
    """The IdP redirects the browser here with an authorization code
    (ADR-0025). Verifies the id_token, JIT-provisions or looks up the user,
    and mints the same session shape password login does."""
    result = await handle_sso_callback(
        session=db, redis=redis, settings=settings, code=code, state=state, transport=transport
    )
    await AuditLogRepository(db).create(
        actor_id=result.user.id,
        action="user.sso_login",
        entity_type="user",
        entity_id=result.user.id,
        ip=_client_ip(request),
    )
    await db.commit()
    return TokenResponse(access=result.access, refresh=result.refresh)
