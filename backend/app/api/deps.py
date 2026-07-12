"""Shared FastAPI dependencies: DB session, Redis, settings, current user, RBAC."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

import httpx
from arq.connections import ArqRedis
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.core.storage import ObjectStorage
from app.core.token_denylist import is_revoked
from app.data.models.user import User, UserRole
from app.data.repositories.user_repository import UserRepository
from app.data.rls import set_rls_user
from app.evidence.registry import EvidenceConnectorRegistry
from app.ingestion.embeddings import EmbeddingModel, get_embedding_model
from app.medication.openfda_ddi_client import OpenFdaDdiClient
from app.medication.rxnorm_client import RxNormClient
from app.providers.registry import ProviderRegistry

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in request.app.state.db.session():
        yield session


async def get_read_db(request: Request) -> AsyncIterator[AsyncSession]:
    """A session on the read replica when one is configured, the primary
    otherwise (ADR-0023) — use for endpoints that only ever read."""
    async for session in request.app.state.db.replica_session():
        yield session


async def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


async def get_arq_pool(request: Request) -> ArqRedis:
    arq_pool: ArqRedis = request.app.state.arq
    return arq_pool


async def get_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage = request.app.state.storage
    return storage


def get_embedding_model_dep(settings: Annotated[Settings, Depends(get_settings)]) -> EmbeddingModel:
    return get_embedding_model(
        settings.EMBEDDING_MODEL_ID,
        settings.EMBEDDING_DEVICE,
        offline_only=settings.is_ollama_only,
    )


async def get_provider_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry = request.app.state.provider_registry
    return registry


async def get_evidence_connector_registry(request: Request) -> EvidenceConnectorRegistry:
    registry: EvidenceConnectorRegistry = request.app.state.evidence_connectors
    return registry


async def get_rxnorm_client(request: Request) -> RxNormClient:
    client: RxNormClient = request.app.state.rxnorm_client
    return client


async def get_openfda_ddi_client(request: Request) -> OpenFdaDdiClient:
    client: OpenFdaDdiClient = request.app.state.openfda_ddi_client
    return client


async def get_sso_http_transport(request: Request) -> httpx.AsyncBaseTransport | None:
    """``None`` in production (the SSO OIDC client makes real requests) —
    exists only so API tests can override this with ``httpx.MockTransport``
    for a full round-trip through the actual endpoint, the same
    dependency-override pattern used for every other external-service
    registry (ADR-0025)."""
    return getattr(request.app.state, "sso_http_transport", None)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
ReadOnlyDbDep = Annotated[AsyncSession, Depends(get_read_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]
ArqDep = Annotated[ArqRedis, Depends(get_arq_pool)]
StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
EmbeddingModelDep = Annotated[EmbeddingModel, Depends(get_embedding_model_dep)]
ProviderRegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]
EvidenceConnectorRegistryDep = Annotated[
    EvidenceConnectorRegistry, Depends(get_evidence_connector_registry)
]
RxNormClientDep = Annotated[RxNormClient, Depends(get_rxnorm_client)]
OpenFdaDdiClientDep = Annotated[OpenFdaDdiClient, Depends(get_openfda_ddi_client)]
SsoHttpTransportDep = Annotated[httpx.AsyncBaseTransport | None, Depends(get_sso_http_transport)]


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


async def get_rls_scoped_read_db(db: ReadOnlyDbDep, user: CurrentUserDep) -> AsyncSession:
    """Like ``get_rls_scoped_db``, but on the read-replica session
    (ADR-0023). The RLS GUC is transaction-local *session* state — never
    replicated between physical connections — so a replica session needs
    this identical per-request setup, not just the primary."""
    await set_rls_user(db, user.id)
    return db


ReadOnlyRlsDbDep = Annotated[AsyncSession, Depends(get_rls_scoped_read_db)]


async def get_streaming_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> User:
    """Like get_current_user, but additionally accepts a short-lived stream
    ticket via a ``?ticket=`` query parameter when no Authorization header is
    present. Used only by the two endpoints the browser connects to directly
    for SSE (ADR-0007) — POST /chats/{id}/messages and GET /jobs/{id}/events —
    never the general auth dependency, so this never broadens what a normal
    (long-lived) access token can be used for."""
    if credentials is not None:
        return await get_current_user(credentials, db, redis, settings)

    ticket = request.query_params.get("ticket")
    if ticket is None:
        raise UnauthorizedError("Missing bearer token or stream ticket.")

    try:
        payload = decode_token(ticket, TokenType.STREAM, settings)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired stream ticket.") from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed ticket subject.") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")
    return user


StreamingUserDep = Annotated[User, Depends(get_streaming_user)]


async def get_rls_scoped_db_streaming(db: DbDep, user: StreamingUserDep) -> AsyncSession:
    await set_rls_user(db, user.id)
    return db


StreamingRlsDbDep = Annotated[AsyncSession, Depends(get_rls_scoped_db_streaming)]


def require_role(*allowed_roles: UserRole) -> Callable[[User], User]:
    def _check(user: CurrentUserDep) -> User:
        if user.role not in allowed_roles:
            raise ForbiddenError(
                f"Role {user.role.value!r} is not permitted to perform this action."
            )
        return user

    return _check
