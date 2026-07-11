"""API tests: Enterprise SSO endpoints (docs/API.md — Auth / Org SSO,
ADR-0025) — RBAC on /org/sso-config, org-scoped isolation, secret-never-
returned, and a full round trip through the real /auth/sso/start and
/auth/sso/callback endpoints with the IdP transport swapped via
get_sso_http_transport's dependency-override (mirroring
get_provider_registry/get_evidence_connector_registry's pattern in
test_evidence_api.py — no real network calls required)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable, Callable

import httpx
import jwt
import pytest
from app.api.deps import get_sso_http_transport
from app.core.config import get_settings
from app.core.security import create_access_token
from app.data.models.organization import Organization
from app.data.models.sso import OrgSsoConfig
from app.data.models.user import User, UserRole
from app.sso.crypto import encrypt_client_secret
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from jwt.algorithms import RSAAlgorithm

pytestmark = pytest.mark.api

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]
_KID = "test-key-1"


@pytest.fixture(autouse=True)
def _sso_encryption_key():  # type: ignore[no-untyped-def]
    """Every /org/sso-config write in this file, and handle_sso_callback's
    decrypt of a stored secret, go through the request-scoped SettingsDep
    (get_settings()) — not a standalone Settings() object — so the key must
    be present in the actual process env for the app under test to see it.
    Restored afterwards so it doesn't leak into other test files sharing
    this process's get_settings() cache."""
    key = Fernet.generate_key().decode("ascii")
    os.environ["SSO_CONFIG_ENCRYPTION_KEY"] = key
    get_settings.cache_clear()
    yield
    del os.environ["SSO_CONFIG_ENCRYPTION_KEY"]
    get_settings.cache_clear()


def _unique_issuer() -> str:
    return f"https://idp-{uuid.uuid4()}.example.com"


async def _make_org_admin(app, *, email: str | None = None) -> tuple[dict[str, str], uuid.UUID]:  # type: ignore[no-untyped-def]
    """Directly provisions an org + an org-admin user (no password — SSO
    admins are ordinary accounts here, this just skips the register/login
    round trip) and mints a real access token for it."""
    settings = get_settings()
    async for session in app.state.db.session():
        org = Organization(name="Test Org")
        session.add(org)
        await session.flush()
        user = User(
            email=email or f"admin-{uuid.uuid4()}@example.com",
            password_hash=None,
            role=UserRole.ORG_ADMIN,
            org_id=org.id,
        )
        session.add(user)
        await session.commit()
        org_id: uuid.UUID = org.id
        user_id = user.id
        break
    token = create_access_token(str(user_id), settings, role=UserRole.ORG_ADMIN.value)
    return {"Authorization": f"Bearer {token}"}, org_id


def _rsa_keypair() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = _KID
    return private_key, jwk


def _idp_transport(
    *,
    issuer: str,
    private_key: rsa.RSAPrivateKey,
    jwk: dict[str, object],
    client_id: str,
    email: str,
) -> tuple[httpx.MockTransport, dict[str, str]]:
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
            claims = {"iss": issuer, "aud": client_id, "email": email, "nonce": nonce}
            id_token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": _KID})
            return httpx.Response(200, json={"id_token": id_token, "access_token": "fake"})
        raise AssertionError(f"unexpected request to {request.url}")

    return httpx.MockTransport(handler), captured


@pytest.mark.asyncio
async def test_upsert_sso_config_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/org/sso-config",
        json={
            "issuer": "https://idp.example.com",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "email_domain": "acme.example.com",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upsert_sso_config_rejects_a_non_org_admin(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("regular-user@example.com")
    response = await client.post(
        "/api/v1/org/sso-config",
        json={
            "issuer": "https://idp.example.com",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "email_domain": "acme.example.com",
        },
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "forbidden"


@pytest.mark.asyncio
async def test_upsert_sso_config_never_returns_the_client_secret(  # type: ignore[no-untyped-def]
    client: AsyncClient, app
) -> None:
    headers, org_id = await _make_org_admin(app)
    domain = f"acme-{uuid.uuid4()}.example.com"
    response = await client.post(
        "/api/v1/org/sso-config",
        json={
            "issuer": "https://idp.example.com",
            "client_id": "client-1",
            "client_secret": "super-secret-value",
            "email_domain": domain,
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert str(org_id) == body["org_id"]
    assert "client_secret" not in body
    assert "client_secret_encrypted" not in body
    assert "super-secret-value" not in response.text


@pytest.mark.asyncio
async def test_get_sso_config_is_404_when_unconfigured(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    headers, _org_id = await _make_org_admin(app)
    response = await client.get("/api/v1/org/sso-config", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sso_config_is_isolated_per_org(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    """One org's admin configuring SSO must never become visible to a
    different org's admin (per-chat/tenant isolation posture, CLAUDE.md §3
    applied to org-scoped resources)."""
    headers_a, _org_a = await _make_org_admin(app)
    headers_b, _org_b = await _make_org_admin(app)

    domain = f"acme-{uuid.uuid4()}.example.com"
    create = await client.post(
        "/api/v1/org/sso-config",
        json={
            "issuer": "https://idp.example.com",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "email_domain": domain,
        },
        headers=headers_a,
    )
    assert create.status_code == 201

    same_org = await client.get("/api/v1/org/sso-config", headers=headers_a)
    assert same_org.status_code == 200

    other_org = await client.get("/api/v1/org/sso-config", headers=headers_b)
    assert other_org.status_code == 404


@pytest.mark.asyncio
async def test_delete_sso_config_requires_org_admin_and_removes_it(  # type: ignore[no-untyped-def]
    client: AsyncClient, app
) -> None:
    headers, _org_id = await _make_org_admin(app)
    domain = f"acme-{uuid.uuid4()}.example.com"
    await client.post(
        "/api/v1/org/sso-config",
        json={
            "issuer": "https://idp.example.com",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "email_domain": domain,
        },
        headers=headers,
    )

    delete = await client.delete("/api/v1/org/sso-config", headers=headers)
    assert delete.status_code == 204

    after = await client.get("/api/v1/org/sso-config", headers=headers)
    assert after.status_code == 404


@pytest.mark.asyncio
async def test_sso_start_is_not_found_for_an_unconfigured_domain(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/sso/start", json={"email": f"user@unconfigured-{uuid.uuid4()}.com"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_full_sso_round_trip_through_the_real_endpoints(  # type: ignore[no-untyped-def]
    client: AsyncClient, app
) -> None:
    """Exercises /auth/sso/start and /auth/sso/callback exactly as the
    browser does — the only network-facing seam (the OIDC client's httpx
    transport) is swapped for a MockTransport via get_sso_http_transport's
    dependency override, the same pattern get_provider_registry /
    get_evidence_connector_registry already use for external services.

    handle_sso_callback decrypts the org's stored client secret using the
    request-scoped SettingsDep (i.e. get_settings()) — the same key the
    _sso_encryption_key autouse fixture has already put in the process env
    for every test in this file, so encrypting the fixture's OrgSsoConfig
    below with get_settings() matches what the real endpoint will resolve."""
    settings = get_settings()
    domain = f"acme-{uuid.uuid4()}.example.com"
    issuer = _unique_issuer()
    client_id = "test-client-id"
    email = f"new-sso-user-{uuid.uuid4()}@{domain}"

    async for session in app.state.db.session():
        org = Organization(name="Test Org")
        session.add(org)
        await session.flush()
        session.add(
            OrgSsoConfig(
                org_id=org.id,
                issuer=issuer,
                client_id=client_id,
                client_secret_encrypted=encrypt_client_secret("client-secret", settings),
                email_domain=domain,
                is_active=True,
            )
        )
        await session.commit()
        break

    private_key, jwk = _rsa_keypair()
    transport, captured = _idp_transport(
        issuer=issuer, private_key=private_key, jwk=jwk, client_id=client_id, email=email
    )
    app.dependency_overrides[get_sso_http_transport] = lambda: transport
    try:
        start = await client.post("/api/v1/auth/sso/start", json={"email": email})
        assert start.status_code == 200
        redirect_url = start.json()["redirect_url"]
        query = httpx.URL(redirect_url).params
        state = query["state"]
        captured["nonce"] = query["nonce"]

        callback = await client.get(
            "/api/v1/auth/sso/callback", params={"code": "fake-auth-code", "state": state}
        )
        assert callback.status_code == 200
        body = callback.json()
        assert body["access"]
        assert body["refresh"]
    finally:
        app.dependency_overrides.pop(get_sso_http_transport, None)
