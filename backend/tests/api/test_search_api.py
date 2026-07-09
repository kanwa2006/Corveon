"""API tests: semantic search (docs/API.md — Search). In-chat only."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import fitz
import pytest
from app.core.config import get_settings
from app.ingestion.embeddings import get_embedding_model
from app.workers.tasks import run_ingestion
from httpx import AsyncClient

pytestmark = pytest.mark.api

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


def _make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    data: bytes = doc.tobytes()
    doc.close()
    return data


async def _ingest_document(
    client: AsyncClient, app, headers: dict[str, str], chat_id: str, text: str
) -> None:  # type: ignore[no-untyped-def]
    upload = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(text), "application/pdf")},
        headers=headers,
    )
    job_id = upload.json()["job_id"]
    documents = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)).json()
    document_id = documents[-1]["id"]
    user_id = (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]

    settings = get_settings()
    await run_ingestion(
        db=app.state.db,
        storage=app.state.storage,
        embedding_model=get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE),
        job_id=uuid.UUID(job_id),
        document_id=uuid.UUID(document_id),
        chat_id=uuid.UUID(chat_id),
        user_id=uuid.UUID(user_id),
    )


@pytest.mark.asyncio
async def test_search_requires_owned_chat(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/search",
        json={"query": "anything"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_returns_empty_list_when_no_documents(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat = await client.post("/api/v1/chats", json={"title": "Empty"}, headers=headers)
    chat_id = chat.json()["id"]

    response = await client.post(
        f"/api/v1/chats/{chat_id}/search", json={"query": "anything"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_search_never_returns_hits_from_a_different_chat(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_a = (await client.post("/api/v1/chats", json={"title": "A"}, headers=headers)).json()["id"]
    chat_b = (await client.post("/api/v1/chats", json={"title": "B"}, headers=headers)).json()["id"]

    await _ingest_document(client, app, headers, chat_a, "Metformin treats type 2 diabetes.")
    await _ingest_document(client, app, headers, chat_b, "Lisinopril treats high blood pressure.")

    response = await client.post(
        f"/api/v1/chats/{chat_a}/search", json={"query": "diabetes medication"}, headers=headers
    )
    hits = response.json()
    assert len(hits) >= 1
    assert all("Metformin" in hit["text"] for hit in hits)


@pytest.mark.asyncio
async def test_search_respects_top_k(client: AsyncClient, auth_headers: AuthHeaders, app) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = (await client.post("/api/v1/chats", json={"title": "C"}, headers=headers)).json()[
        "id"
    ]
    long_text = "\n\n".join(f"Fact number {i} about clinical topic {i}." for i in range(20))
    await _ingest_document(client, app, headers, chat_id, long_text)

    response = await client.post(
        f"/api/v1/chats/{chat_id}/search",
        json={"query": "clinical topic", "top_k": 2},
        headers=headers,
    )
    assert response.status_code == 200
    assert len(response.json()) <= 2
