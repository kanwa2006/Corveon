"""Audit log tests: sensitive actions actually produce append-only audit
rows (CLAUDE.md §8), verified by querying the table directly — there is no
admin-facing read endpoint yet, so this is the ground truth for now."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import fitz
import pytest
from app.api.deps import get_provider_registry
from app.data.models.audit_log import AuditLog
from app.providers.base import ChatMessage, ChatProvider
from app.providers.registry import ProviderRegistry
from httpx import AsyncClient
from sqlalchemy import select

pytestmark = [pytest.mark.database]


class _StubProvider(ChatProvider):
    name = "stub"

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        yield "Hello."


async def _audit_rows(app, action: str) -> list[AuditLog]:  # type: ignore[no-untyped-def]
    async for session in app.state.db.session():
        result = await session.execute(select(AuditLog).where(AuditLog.action == action))
        return list(result.scalars().all())
    return []


@pytest.mark.asyncio
async def test_register_creates_an_audit_entry(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    email = "audit-register@example.com"
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correcthorsebattery"}
    )
    user_id = response.json()["id"]

    rows = await _audit_rows(app, "user.register")
    assert any(str(row.actor_id) == user_id for row in rows)


@pytest.mark.asyncio
async def test_login_creates_an_audit_entry(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    email = "audit-login@example.com"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correcthorsebattery"}
    )
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correcthorsebattery"}
    )
    assert login_response.status_code == 200

    rows = await _audit_rows(app, "user.login")
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_logout_creates_an_audit_entry(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    email = "audit-logout@example.com"
    password = "correcthorsebattery"
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    tokens = login.json()

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh"]},
        headers={"Authorization": f"Bearer {tokens['access']}"},
    )
    assert response.status_code == 204

    rows = await _audit_rows(app, "user.logout")
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_document_upload_and_delete_create_audit_entries(
    client: AsyncClient,
    app,  # type: ignore[no-untyped-def]
) -> None:
    email = "audit-docs@example.com"
    password = "correcthorsebattery"
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access']}"}

    chat_response = await client.post(
        "/api/v1/chats", json={"title": "Audit chat"}, headers=headers
    )
    chat_id = chat_response.json()["id"]

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Audit test content.")
    pdf_bytes = doc.tobytes()
    doc.close()

    await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("audit.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    documents = await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)
    document_id = documents.json()[0]["id"]

    upload_rows = await _audit_rows(app, "document.upload")
    assert any(str(row.entity_id) == document_id for row in upload_rows)

    delete_response = await client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert delete_response.status_code == 204

    delete_rows = await _audit_rows(app, "document.delete")
    assert any(str(row.entity_id) == document_id for row in delete_rows)


@pytest.mark.asyncio
async def test_chat_delete_creates_an_audit_entry(
    client: AsyncClient,
    app,  # type: ignore[no-untyped-def]
) -> None:
    """CORVEON blueprint §23.6: hard-deleting a chat must record a single
    audit-log entry for the action (not the content it cascaded away)."""
    email = "audit-chat-delete@example.com"
    password = "correcthorsebattery"
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access']}"}

    chat_response = await client.post("/api/v1/chats", json={"title": "Bye chat"}, headers=headers)
    chat_id = chat_response.json()["id"]

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Content to be cascaded away.")
    pdf_bytes = doc.tobytes()
    doc.close()
    await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("bye.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )

    delete_response = await client.delete(f"/api/v1/chats/{chat_id}", headers=headers)
    assert delete_response.status_code == 204

    rows = await _audit_rows(app, "chat.delete")
    matching = [row for row in rows if str(row.entity_id) == chat_id]
    assert len(matching) == 1
    assert matching[0].audit_metadata == {"document_count": 1}


@pytest.mark.asyncio
async def test_message_export_creates_an_audit_entry(
    client: AsyncClient,
    app,  # type: ignore[no-untyped-def]
) -> None:
    email = "audit-export@example.com"
    password = "correcthorsebattery"
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access']}"}

    chat_response = await client.post("/api/v1/chats", json={"title": "Chat"}, headers=headers)
    chat_id = chat_response.json()["id"]

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider()}, ["stub"]
    )
    try:
        async with client.stream(
            "POST", f"/api/v1/chats/{chat_id}/messages", json={"content": "hi"}, headers=headers
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)

    events = [
        line for line in raw.decode().replace("\r\n", "\n").split("\n\n") if "event: done" in line
    ]
    done_data = json.loads(events[0].split("data: ", 1)[1])
    message_id = done_data["message_id"]

    export_response = await client.post(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/export",
        json={"format": "md"},
        headers=headers,
    )
    assert export_response.status_code == 200

    rows = await _audit_rows(app, "message.export")
    assert any(str(row.entity_id) == message_id for row in rows)
