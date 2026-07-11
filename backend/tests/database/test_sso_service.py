"""Service-level tests for app/sso/service.py (ADR-0025) — the full
start-login + callback flow against a mocked IdP (httpx.MockTransport,
matching every other external-service test in this codebase), a real
Postgres session (via the ``app`` fixture) and real Redis for the
state/nonce/PKCE single-use attempt store."""

from __future__ import annotations

import urllib.parse
import uuid

import httpx
import jwt
import pytest
from app.core.config import Settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError, ValidationAppError
from app.data.models.organization import Organization
from app.data.models.sso import OrgSsoConfig
from app.data.models.user import User, UserRole
from app.sso.crypto import encrypt_client_secret
from app.sso.oidc_client import IdTokenVerificationError
from app.sso.service import handle_sso_callback, start_sso_login
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select

pytestmark = [pytest.mark.database]

_KID = "test-key-1"
_SSO_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")


def _unique_issuer() -> str:
    # fetch_discovery_document caches in Redis keyed only by issuer, and
    # nothing in this suite flushes Redis between tests (conftest.py's
    # _clean_tables truncates SQL tables only, never app.state.redis) — a
    # literal issuer shared across tests/files causes cross-test cache
    # pollution. A unique issuer per test sidesteps this entirely.
    return f"https://idp-{uuid.uuid4()}.example.com"


def _test_settings() -> Settings:
    # A local Settings object rather than the ambient get_settings() cache —
    # SSO_CONFIG_ENCRYPTION_KEY is only required once an org actually saves
    # an SSO config (§23.1's "absence is normal" posture), so it isn't part
    # of the shared test environment conftest.py sets up.
    return Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        SSO_CONFIG_ENCRYPTION_KEY=_SSO_ENCRYPTION_KEY,
    )


def _rsa_keypair() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = _KID
    return private_key, jwk


async def _create_org_with_sso(  # type: ignore[no-untyped-def]
    app,
    *,
    issuer: str,
    email_domain: str,
    client_id: str = "test-client-id",
    is_active: bool = True,
) -> tuple[uuid.UUID, str]:
    settings = _test_settings()
    async for session in app.state.db.session():
        org = Organization(name="Test Org")
        session.add(org)
        await session.flush()
        config = OrgSsoConfig(
            org_id=org.id,
            issuer=issuer,
            client_id=client_id,
            client_secret_encrypted=encrypt_client_secret("client-secret", settings),
            email_domain=email_domain,
            is_active=is_active,
        )
        session.add(config)
        await session.commit()
        org_id: uuid.UUID = org.id
        break
    return org_id, client_id


def _idp_transport(
    *,
    issuer: str,
    private_key: rsa.RSAPrivateKey,
    jwk: dict[str, object],
    client_id: str,
    email: str | None,
) -> tuple[httpx.MockTransport, dict[str, str]]:
    """A fake IdP serving discovery/token/jwks. ``captured`` records the
    nonce the token endpoint was asked to embed, populated only after
    handle_sso_callback actually calls the token endpoint (the nonce isn't
    known until start_sso_login runs)."""
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": f"{issuer}/authorize",
                    "token_endpoint": f"{issuer}/token",
                    "jwks_uri": f"{issuer}/jwks",
                },
            )
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path == "/token":
            nonce = captured["nonce"]
            claims: dict[str, object] = {"iss": issuer, "aud": client_id, "nonce": nonce}
            if email is not None:
                claims["email"] = email
            id_token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": _KID})
            return httpx.Response(200, json={"id_token": id_token, "access_token": "fake"})
        raise AssertionError(f"unexpected request to {request.url}")

    return httpx.MockTransport(handler), captured


async def _start_and_extract_state_and_nonce(  # type: ignore[no-untyped-def]
    app,
    *,
    email: str,
    transport: httpx.MockTransport,
) -> tuple[str, str]:
    settings = _test_settings()
    async for session in app.state.db.session():
        redirect_url = await start_sso_login(
            session=session,
            redis=app.state.redis,
            settings=settings,
            email=email,
            transport=transport,
        )
        break
    query = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
    return query["state"][0], query["nonce"][0]


async def test_start_sso_login_raises_not_found_for_an_unconfigured_domain(app) -> None:  # type: ignore[no-untyped-def]
    settings = _test_settings()
    async for session in app.state.db.session():
        with pytest.raises(NotFoundError):
            await start_sso_login(
                session=session,
                redis=app.state.redis,
                settings=settings,
                email=f"user@unconfigured-{uuid.uuid4()}.com",
            )
        break


async def test_start_sso_login_raises_not_found_for_an_inactive_config(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"inactive-{uuid.uuid4()}.example.com"
    await _create_org_with_sso(app, issuer=_unique_issuer(), email_domain=domain, is_active=False)

    settings = _test_settings()
    async for session in app.state.db.session():
        with pytest.raises(NotFoundError):
            await start_sso_login(
                session=session, redis=app.state.redis, settings=settings, email=f"user@{domain}"
            )
        break


async def test_start_sso_login_rejects_a_malformed_email(app) -> None:  # type: ignore[no-untyped-def]
    settings = _test_settings()
    async for session in app.state.db.session():
        with pytest.raises(ValidationAppError):
            await start_sso_login(
                session=session, redis=app.state.redis, settings=settings, email="not-an-email"
            )
        break


async def test_start_sso_login_returns_an_authorization_url(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    _org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    transport, _captured = _idp_transport(
        issuer=issuer,
        private_key=private_key,
        jwk=jwk,
        client_id=client_id,
        email="anyone@example.com",
    )

    state, nonce = await _start_and_extract_state_and_nonce(
        app, email=f"user@{domain}", transport=transport
    )
    assert state
    assert nonce


async def test_full_callback_flow_jit_provisions_a_new_user(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    email = f"new-sso-user-{uuid.uuid4()}@{domain}"
    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
    )

    state, nonce = await _start_and_extract_state_and_nonce(app, email=email, transport=transport)
    captured["nonce"] = nonce

    settings = _test_settings()
    async for session in app.state.db.session():
        result = await handle_sso_callback(
            session=session,
            redis=app.state.redis,
            settings=settings,
            code="fake-auth-code",
            state=state,
            transport=transport,
        )
        break

    assert result.access
    assert result.refresh
    assert result.user.email == email
    assert result.user.org_id == org_id
    assert result.user.password_hash is None


async def test_callback_finds_the_existing_user_on_a_second_login(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    _org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    email = f"repeat-sso-user-{uuid.uuid4()}@{domain}"
    settings = _test_settings()

    first_user_id: uuid.UUID | None = None
    for _ in range(2):
        transport, captured = _idp_transport(
            issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
        )
        state, nonce = await _start_and_extract_state_and_nonce(
            app, email=email, transport=transport
        )
        captured["nonce"] = nonce
        async for session in app.state.db.session():
            result = await handle_sso_callback(
                session=session,
                redis=app.state.redis,
                settings=settings,
                code="fake-auth-code",
                state=state,
                transport=transport,
            )
            break
        if first_user_id is None:
            first_user_id = result.user.id
        else:
            assert result.user.id == first_user_id


async def test_callback_rejects_an_existing_user_from_a_different_org(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    _org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()

    # An existing user with this email, already tied to a *different* org
    # (e.g. registered directly, or provisioned by a different org's SSO).
    email = f"cross-org-{uuid.uuid4()}@{domain}"
    settings = _test_settings()
    async for session in app.state.db.session():
        other_org = Organization(name="Some Other Org")
        session.add(other_org)
        await session.flush()
        session.add(User(email=email, password_hash=None, org_id=other_org.id))
        await session.commit()
        break

    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
    )
    state, nonce = await _start_and_extract_state_and_nonce(app, email=email, transport=transport)
    captured["nonce"] = nonce

    async for session in app.state.db.session():
        with pytest.raises(ForbiddenError):
            await handle_sso_callback(
                session=session,
                redis=app.state.redis,
                settings=settings,
                code="fake-auth-code",
                state=state,
                transport=transport,
            )
        break


async def test_callback_rejects_an_inactive_user(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    email = f"inactive-sso-user-{uuid.uuid4()}@{domain}"
    settings = _test_settings()

    async for session in app.state.db.session():
        session.add(User(email=email, password_hash=None, org_id=org_id, is_active=False))
        await session.commit()
        break

    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
    )
    state, nonce = await _start_and_extract_state_and_nonce(app, email=email, transport=transport)
    captured["nonce"] = nonce

    async for session in app.state.db.session():
        with pytest.raises(UnauthorizedError):
            await handle_sso_callback(
                session=session,
                redis=app.state.redis,
                settings=settings,
                code="fake-auth-code",
                state=state,
                transport=transport,
            )
        break


async def test_callback_rejects_an_unknown_state(app) -> None:  # type: ignore[no-untyped-def]
    settings = _test_settings()
    async for session in app.state.db.session():
        with pytest.raises(UnauthorizedError):
            await handle_sso_callback(
                session=session,
                redis=app.state.redis,
                settings=settings,
                code="fake-auth-code",
                state="a-state-that-was-never-issued",
            )
        break


async def test_callback_rejects_a_state_reused_after_first_success(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    _org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    email = f"replay-{uuid.uuid4()}@{domain}"
    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
    )

    state, nonce = await _start_and_extract_state_and_nonce(app, email=email, transport=transport)
    captured["nonce"] = nonce

    settings = _test_settings()
    async for session in app.state.db.session():
        await handle_sso_callback(
            session=session,
            redis=app.state.redis,
            settings=settings,
            code="fake-auth-code",
            state=state,
            transport=transport,
        )
        break

    # Same state again — must fail, single-use (CSRF/replay protection).
    async for session in app.state.db.session():
        with pytest.raises(UnauthorizedError):
            await handle_sso_callback(
                session=session,
                redis=app.state.redis,
                settings=settings,
                code="fake-auth-code",
                state=state,
                transport=transport,
            )
        break


async def test_callback_rejects_a_missing_email_claim(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    _org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=None
    )

    state, nonce = await _start_and_extract_state_and_nonce(
        app, email=f"user@{domain}", transport=transport
    )
    captured["nonce"] = nonce

    settings = _test_settings()
    async for session in app.state.db.session():
        with pytest.raises(IdTokenVerificationError, match="email"):
            await handle_sso_callback(
                session=session,
                redis=app.state.redis,
                settings=settings,
                code="fake-auth-code",
                state=state,
                transport=transport,
            )
        break


async def test_jit_provisioned_user_has_the_default_role(app) -> None:  # type: ignore[no-untyped-def]
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    org_id, client_id = await _create_org_with_sso(app, issuer=issuer, email_domain=domain)
    private_key, jwk = _rsa_keypair()
    email = f"role-check-{uuid.uuid4()}@{domain}"
    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
    )
    state, nonce = await _start_and_extract_state_and_nonce(app, email=email, transport=transport)
    captured["nonce"] = nonce

    settings = _test_settings()
    async for session in app.state.db.session():
        result = await handle_sso_callback(
            session=session,
            redis=app.state.redis,
            settings=settings,
            code="fake-auth-code",
            state=state,
            transport=transport,
        )
        break

    assert result.user.role == UserRole.USER

    async for session in app.state.db.session():
        row = await session.execute(select(User).where(User.id == result.user.id))
        assert row.scalar_one().org_id == org_id
        break
