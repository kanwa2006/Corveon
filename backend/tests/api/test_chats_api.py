"""API tests: chat CRUD, ownership isolation, filtering (docs/API.md — Chats)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.api

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


@pytest.mark.asyncio
async def test_create_chat_with_title(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.post("/api/v1/chats", json={"title": "My First Chat"}, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "My First Chat"
    assert body["is_pinned"] is False
    assert body["is_archived"] is False
    assert body["org_id"] is None


@pytest.mark.asyncio
async def test_create_chat_defaults_title_when_omitted(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.post("/api/v1/chats", json={}, headers=headers)
    assert response.status_code == 201
    assert response.json()["title"] == "New chat"


@pytest.mark.asyncio
async def test_create_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chats", json={"title": "x"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_chats_only_shows_own_chats(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")

    await client.post("/api/v1/chats", json={"title": "Alice chat"}, headers=alice)
    await client.post("/api/v1/chats", json={"title": "Bob chat"}, headers=bob)

    alice_list = await client.get("/api/v1/chats", headers=alice)
    bob_list = await client.get("/api/v1/chats", headers=bob)

    assert [c["title"] for c in alice_list.json()] == ["Alice chat"]
    assert [c["title"] for c in bob_list.json()] == ["Bob chat"]


@pytest.mark.asyncio
async def test_get_chat_by_id_not_owner_is_404(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")

    created = await client.post("/api/v1/chats", json={"title": "Secret"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.get(f"/api/v1/chats/{chat_id}", headers=bob)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_chat_by_id_owner_succeeds(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Mine"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.get(f"/api/v1/chats/{chat_id}", headers=alice)
    assert response.status_code == 200
    assert response.json()["title"] == "Mine"


@pytest.mark.asyncio
async def test_get_nonexistent_chat_is_404(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    response = await client.get("/api/v1/chats/00000000-0000-0000-0000-000000000000", headers=alice)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_rename_and_pin(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Old"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/chats/{chat_id}",
        json={"title": "New", "is_pinned": True},
        headers=alice,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New"
    assert body["is_pinned"] is True


@pytest.mark.asyncio
async def test_patch_is_partial(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Untouched"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/chats/{chat_id}", json={"is_pinned": True}, headers=alice
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Untouched"
    assert response.json()["is_pinned"] is True


@pytest.mark.asyncio
async def test_patch_title_with_nul_byte_is_422_not_500(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    # Postgres text columns reject an embedded NUL byte at the wire level
    # (asyncpg CharacterNotInRepertoireError); a Python str otherwise allows
    # it freely, so this must be rejected at the Pydantic validation layer
    # rather than surfacing as an unhandled 500 from the DB driver — found
    # by the schemathesis contract job (CI).
    alice = await auth_headers("alice@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Old"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/chats/{chat_id}", json={"title": "bad\x00title"}, headers=alice
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_not_owner_is_404(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Alice's"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.patch(f"/api/v1/chats/{chat_id}", json={"title": "Hacked"}, headers=bob)
    assert response.status_code == 404

    unchanged = await client.get(f"/api/v1/chats/{chat_id}", headers=alice)
    assert unchanged.json()["title"] == "Alice's"


@pytest.mark.asyncio
async def test_delete_not_owner_is_404_and_chat_survives(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Alice's"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.delete(f"/api/v1/chats/{chat_id}", headers=bob)
    assert response.status_code == 404

    still_there = await client.get(f"/api/v1/chats/{chat_id}", headers=alice)
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_delete_own_chat(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    created = await client.post("/api/v1/chats", json={"title": "Bye"}, headers=alice)
    chat_id = created.json()["id"]

    response = await client.delete(f"/api/v1/chats/{chat_id}", headers=alice)
    assert response.status_code == 204

    gone = await client.get(f"/api/v1/chats/{chat_id}", headers=alice)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_search_filter(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    await client.post("/api/v1/chats", json={"title": "Renal dosing question"}, headers=alice)
    await client.post("/api/v1/chats", json={"title": "Unrelated chat"}, headers=alice)

    response = await client.get("/api/v1/chats?search=renal", headers=alice)
    assert response.status_code == 200
    titles = [c["title"] for c in response.json()]
    assert titles == ["Renal dosing question"]


@pytest.mark.asyncio
async def test_pinned_filter(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    pinned = await client.post("/api/v1/chats", json={"title": "Pinned"}, headers=alice)
    await client.post("/api/v1/chats", json={"title": "Not pinned"}, headers=alice)
    await client.patch(
        f"/api/v1/chats/{pinned.json()['id']}", json={"is_pinned": True}, headers=alice
    )

    response = await client.get("/api/v1/chats?pinned=true", headers=alice)
    titles = [c["title"] for c in response.json()]
    assert titles == ["Pinned"]


@pytest.mark.asyncio
async def test_archived_chats_hidden_by_default(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    archived = await client.post("/api/v1/chats", json={"title": "Archived"}, headers=alice)
    await client.post("/api/v1/chats", json={"title": "Active"}, headers=alice)
    await client.patch(
        f"/api/v1/chats/{archived.json()['id']}", json={"is_archived": True}, headers=alice
    )

    default_list = await client.get("/api/v1/chats", headers=alice)
    assert [c["title"] for c in default_list.json()] == ["Active"]

    archived_list = await client.get("/api/v1/chats?archived=true", headers=alice)
    assert [c["title"] for c in archived_list.json()] == ["Archived"]


@pytest.mark.asyncio
async def test_pinned_chats_ordered_before_unpinned(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    await client.post("/api/v1/chats", json={"title": "First"}, headers=alice)
    second = await client.post("/api/v1/chats", json={"title": "Second"}, headers=alice)
    await client.patch(
        f"/api/v1/chats/{second.json()['id']}", json={"is_pinned": True}, headers=alice
    )

    response = await client.get("/api/v1/chats", headers=alice)
    titles = [c["title"] for c in response.json()]
    assert titles[0] == "Second"  # pinned sorts first regardless of creation order
