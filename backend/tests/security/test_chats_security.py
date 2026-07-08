"""Security tests: chat endpoints reject unauthenticated access and treat
search input as plain data, never as SQL."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.security

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


@pytest.mark.asyncio
async def test_list_chats_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/chats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/chats/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000", json={"title": "x"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.delete("/api/v1/chats/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_with_sql_special_characters_is_treated_as_plain_data(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    await client.post("/api/v1/chats", json={"title": "Normal chat"}, headers=alice)

    payload = "'; DROP TABLE chats;--"
    response = await client.get("/api/v1/chats", params={"search": payload}, headers=alice)
    # The ORM always parameterizes queries — this proves the table survives
    # and simply yields no matches, rather than executing as SQL.
    assert response.status_code == 200
    assert response.json() == []

    still_there = await client.get("/api/v1/chats", headers=alice)
    assert len(still_there.json()) == 1


@pytest.mark.asyncio
async def test_malformed_chat_id_is_rejected_not_500(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    response = await client.get("/api/v1/chats/not-a-valid-uuid", headers=alice)
    assert response.status_code == 422
