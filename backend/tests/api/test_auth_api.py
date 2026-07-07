"""API tests: register/login/refresh/logout flows (docs/API.md — Auth)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.api


async def _register(
    client: AsyncClient, email: str = "alice@example.com", password: str = "correcthorsebattery"
):
    return await client.post("/api/v1/auth/register", json={"email": email, "password": password})


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient) -> None:
    response = await _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_register_duplicate_email_is_conflict(client: AsyncClient) -> None:
    await _register(client)
    response = await _register(client)
    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "conflict"
    assert "trace_id" in body


@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await _register(client, password="short")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_succeeds_and_returns_tokens(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correcthorsebattery"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access" in body
    assert "refresh" in body


@pytest.mark.asyncio
async def test_login_wrong_password_is_unauthorized(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "unauthorized"


@pytest.mark.asyncio
async def test_login_unknown_email_is_unauthorized(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever12345"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_new_access_token(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correcthorsebattery"},
    )
    refresh_token = login.json()["refresh"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert "access" in response.json()


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correcthorsebattery"},
    )
    access_token = login.json()["access"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correcthorsebattery"},
    )
    tokens = login.json()

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh"]},
        headers={"Authorization": f"Bearer {tokens['access']}"},
    )
    assert logout.status_code == 204

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh"]})
    assert replay.status_code == 401
    assert replay.json()["error_code"] == "unauthorized"


@pytest.mark.asyncio
async def test_logout_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_refresh_token_is_idempotent(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correcthorsebattery"},
    )
    access_token = login.json()["access"]

    response = await client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_endpoint_reports_healthy(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
