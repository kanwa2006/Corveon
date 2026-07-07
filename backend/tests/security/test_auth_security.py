"""Security tests: RBAC enforcement, no credential leakage, malformed tokens."""

from __future__ import annotations

import uuid

import pytest
from app.api.deps import require_role
from app.core.errors import ForbiddenError
from app.data.models.user import User, UserRole
from httpx import AsyncClient

pytestmark = pytest.mark.security


def _make_user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        email="x@example.com",
        password_hash="argon2-hash-placeholder",
        role=role,
        is_active=True,
    )


def test_require_role_allows_matching_role() -> None:
    checker = require_role(UserRole.SUPERADMIN)
    user = _make_user(UserRole.SUPERADMIN)
    assert checker(user) is user


def test_require_role_blocks_non_matching_role() -> None:
    checker = require_role(UserRole.SUPERADMIN)
    user = _make_user(UserRole.USER)
    with pytest.raises(ForbiddenError):
        checker(user)


def test_require_role_allows_any_of_multiple_roles() -> None:
    checker = require_role(UserRole.ORG_ADMIN, UserRole.SUPERADMIN)
    org_admin = _make_user(UserRole.ORG_ADMIN)
    superadmin = _make_user(UserRole.SUPERADMIN)
    assert checker(org_admin) is org_admin
    assert checker(superadmin) is superadmin


@pytest.mark.asyncio
async def test_register_response_never_leaks_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "correcthorsebattery"},
    )
    assert "password" not in response.text
    assert "password_hash" not in response.text


@pytest.mark.asyncio
async def test_login_response_never_leaks_password_hash(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "correcthorsebattery"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "correcthorsebattery"},
    )
    assert "password_hash" not in response.text


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_non_bearer_scheme(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Authorization": "Token abcdef"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sql_injection_style_email_is_treated_as_plain_data(client: AsyncClient) -> None:
    payload = {"email": "not-an-email'; DROP TABLE users;--", "password": "correcthorsebattery"}
    response = await client.post("/api/v1/auth/register", json=payload)
    # Rejected by EmailStr validation, not executed as SQL — the ORM always
    # parameterizes queries, but invalid input should never even reach it.
    assert response.status_code == 422
