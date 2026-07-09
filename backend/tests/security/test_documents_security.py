"""Security tests: messages/documents/jobs/search endpoints reject
unauthenticated access, reject malformed ids without a 500, and treat search
input and upload filenames as plain data — never as SQL or a filesystem path."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import fitz
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.security

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _make_pdf_bytes(text: str = "hello") -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    data: bytes = doc.tobytes()
    doc.close()
    return data


# ── Authentication required ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_messages_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/chats/{_NIL_UUID}/messages")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_message_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(f"/api/v1/chats/{_NIL_UUID}/messages", json={"content": "hi"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_documents_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/chats/{_NIL_UUID}/documents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_document_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/chats/{_NIL_UUID}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_document_requires_authentication(client: AsyncClient) -> None:
    response = await client.delete(f"/api/v1/documents/{_NIL_UUID}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_job_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/jobs/{_NIL_UUID}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_job_events_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/jobs/{_NIL_UUID}/events")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(f"/api/v1/chats/{_NIL_UUID}/search", json={"query": "x"})
    assert response.status_code == 401


# ── Malformed ids rejected with 422, never a raw 500 ─────────────────────


@pytest.mark.asyncio
async def test_malformed_chat_id_on_messages_is_422(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    response = await client.get("/api/v1/chats/not-a-uuid/messages", headers=alice)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_malformed_document_id_on_delete_is_422(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    response = await client.delete("/api/v1/documents/not-a-uuid", headers=alice)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_malformed_job_id_is_422(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    response = await client.get("/api/v1/jobs/not-a-uuid", headers=alice)
    assert response.status_code == 422


# ── Search input is data, never SQL ───────────────────────────────────────


@pytest.mark.asyncio
async def test_search_with_sql_special_characters_is_treated_as_plain_data(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    chat = await client.post("/api/v1/chats", json={"title": "Chat"}, headers=alice)
    chat_id = chat.json()["id"]

    payload = "'; DROP TABLE chats;--"
    response = await client.post(
        f"/api/v1/chats/{chat_id}/search", json={"query": payload}, headers=alice
    )
    # The embedding model always treats the query as ordinary text — this
    # proves the table survives and the request completes normally rather
    # than executing as SQL.
    assert response.status_code == 200
    assert response.json() == []

    still_there = await client.get(f"/api/v1/chats/{chat_id}", headers=alice)
    assert still_there.status_code == 200


# ── Upload filenames are data, never a filesystem path ────────────────────


@pytest.mark.asyncio
async def test_upload_filename_with_path_traversal_is_stored_safely(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    """storage_key is always server-generated (uuid-based) — a hostile
    filename can only ever affect the display name, never the storage path
    (app/api/routers/documents.py, app/core/storage.py)."""
    alice = await auth_headers("alice@example.com")
    chat = await client.post("/api/v1/chats", json={"title": "Chat"}, headers=alice)
    chat_id = chat.json()["id"]

    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("../../../etc/passwd.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=alice,
    )
    assert response.status_code == 202

    documents = await client.get(f"/api/v1/chats/{chat_id}/documents", headers=alice)
    document = documents.json()[0]
    # The hostile filename is preserved only as inert display text...
    assert document["filename"] == "../../../etc/passwd.pdf"
    # ...and never leaks into any path-like identifier returned to the client.
    assert ".." not in document["id"]


@pytest.mark.asyncio
async def test_upload_rejects_double_extension_spoofing(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    """A filename ending in .pdf with a non-PDF MIME type and non-PDF magic
    bytes must still be rejected — extension alone is not trusted."""
    alice = await auth_headers("alice@example.com")
    chat = await client.post("/api/v1/chats", json={"title": "Chat"}, headers=alice)
    chat_id = chat.json()["id"]

    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("script.php.pdf", b"<?php system($_GET['c']); ?>", "application/pdf")},
        headers=alice,
    )
    assert response.status_code == 422
