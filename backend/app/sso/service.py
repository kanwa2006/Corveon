"""SSO login orchestration (ADR-0025): org lookup by email domain, the
Redis-backed single-use login attempt (state/nonce/PKCE verifier), the IdP
round-trip, and JIT user provisioning. Mints a session through the same
``create_access_token``/``create_refresh_token`` every other login path
uses (app/core/security.py) — nothing downstream of this module needs to
know a user authenticated via SSO rather than a password."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError, ValidationAppError
from app.core.security import create_access_token, create_refresh_token
from app.data.models.user import User
from app.data.repositories.sso_config_repository import SsoConfigRepository
from app.data.repositories.user_repository import UserRepository
from app.sso.crypto import decrypt_client_secret
from app.sso.oidc_client import (
    IdTokenVerificationError,
    OidcDiscoveryError,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_discovery_document,
    fetch_jwks,
    generate_nonce,
    generate_pkce_pair,
    generate_state,
    verify_id_token,
)

_STATE_TTL_SECONDS = 300
_STATE_KEY_PREFIX = "sso:state:"


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.FRONTEND_ORIGIN}/api/auth/sso/callback"


def _email_domain(email: str) -> str:
    if "@" not in email:
        raise ValidationAppError("A valid email address is required.")
    domain = email.strip().lower().rsplit("@", 1)[-1]
    if not domain:
        raise ValidationAppError("A valid email address is required.")
    return domain


async def _store_login_attempt(
    redis: Redis, *, state: str, code_verifier: str, nonce: str, org_id: uuid.UUID
) -> None:
    payload = json.dumps({"code_verifier": code_verifier, "nonce": nonce, "org_id": str(org_id)})
    await redis.set(f"{_STATE_KEY_PREFIX}{state}", payload, ex=_STATE_TTL_SECONDS)


async def _pop_login_attempt(redis: Redis, *, state: str) -> dict[str, str] | None:
    key = f"{_STATE_KEY_PREFIX}{state}"
    payload = await redis.get(key)
    if payload is None:
        return None
    await redis.delete(key)  # single-use — a replayed state must fail
    result: dict[str, str] = json.loads(payload)
    return result


async def start_sso_login(
    *,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    email: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Returns the IdP authorization URL to redirect the browser to.
    Raises NotFoundError if no organization has SSO configured for this
    email's domain."""
    domain = _email_domain(email)
    config = await SsoConfigRepository(session).get_by_email_domain(domain)
    if config is None or not config.is_active:
        raise NotFoundError("SSO is not configured for this email domain.")

    discovery = await fetch_discovery_document(
        redis=redis, issuer=config.issuer, transport=transport
    )
    authorization_endpoint = discovery.get("authorization_endpoint")
    if not isinstance(authorization_endpoint, str):
        raise OidcDiscoveryError("Discovery document has no authorization_endpoint.")

    pkce = generate_pkce_pair()
    state = generate_state()
    nonce = generate_nonce()
    await _store_login_attempt(
        redis, state=state, code_verifier=pkce.verifier, nonce=nonce, org_id=config.org_id
    )

    return build_authorization_url(
        authorization_endpoint=authorization_endpoint,
        client_id=config.client_id,
        redirect_uri=_redirect_uri(settings),
        state=state,
        nonce=nonce,
        code_challenge=pkce.challenge,
    )


@dataclass(frozen=True, slots=True)
class SsoSession:
    access: str
    refresh: str
    user: User


async def handle_sso_callback(
    *,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    code: str,
    state: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SsoSession:
    attempt = await _pop_login_attempt(redis, state=state)
    if attempt is None:
        raise UnauthorizedError("Invalid or expired SSO login attempt.")

    org_id = uuid.UUID(attempt["org_id"])
    config_repo = SsoConfigRepository(session)
    config = await config_repo.get_by_org_id(org_id)
    if config is None or not config.is_active:
        raise UnauthorizedError("SSO is no longer configured for this organization.")

    discovery = await fetch_discovery_document(
        redis=redis, issuer=config.issuer, transport=transport
    )
    token_endpoint = discovery.get("token_endpoint")
    jwks_uri = discovery.get("jwks_uri")
    if not isinstance(token_endpoint, str) or not isinstance(jwks_uri, str):
        raise OidcDiscoveryError("Discovery document is missing token_endpoint/jwks_uri.")

    client_secret = decrypt_client_secret(config.client_secret_encrypted, settings)
    tokens = await exchange_code_for_tokens(
        token_endpoint=token_endpoint,
        client_id=config.client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=_redirect_uri(settings),
        code_verifier=attempt["code_verifier"],
        transport=transport,
    )
    id_token = tokens.get("id_token")
    if not isinstance(id_token, str):
        raise IdTokenVerificationError("IdP token response did not include an id_token.")

    jwks = await fetch_jwks(redis=redis, jwks_uri=jwks_uri, transport=transport)
    claims = verify_id_token(
        id_token=id_token,
        jwks=jwks,
        issuer=config.issuer,
        audience=config.client_id,
        nonce=attempt["nonce"],
    )
    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise IdTokenVerificationError("id_token did not include an email claim.")

    user = await UserRepository(session).get_or_create_sso_user(email=email, org_id=org_id)
    if user.org_id != org_id:
        # Never let a login silently move a user across the isolation
        # boundary — a misconfigured or malicious IdP asserting a real
        # email address from a different org must not grant that org's
        # SSO access to an existing account it doesn't own.
        raise ForbiddenError("This account belongs to a different organization.")
    if not user.is_active:
        raise UnauthorizedError("This account is inactive.")

    await session.commit()

    return SsoSession(
        access=create_access_token(str(user.id), settings, role=user.role.value),
        refresh=create_refresh_token(str(user.id), settings),
        user=user,
    )
