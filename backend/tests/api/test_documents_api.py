"""API tests: document upload validation, the full ingestion pipeline, and
listing/deletion (docs/API.md — Documents/uploads). The ARQ worker process
isn't run in tests — ``run_ingestion`` (the same pure function the real
``arq app.workers.main.WorkerSettings`` worker calls) is invoked directly
in-process, matching how ARQ task functions are conventionally tested."""

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

_DIABETES_TEXT = "Metformin is a first-line treatment for type 2 diabetes."


def _make_pdf_bytes(text: str = _DIABETES_TEXT) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data: bytes = doc.tobytes()
    doc.close()
    return data


async def _create_chat(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/v1/chats", json={"title": "Doc chat"}, headers=headers)
    chat_id: str = response.json()["id"]
    return chat_id


async def _current_user_id(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.get("/api/v1/auth/me", headers=headers)
    user_id: str = response.json()["id"]
    return user_id


async def _run_worker(app, job_id: str, document_id: str, chat_id: str, user_id: str) -> None:  # type: ignore[no-untyped-def]
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
async def test_upload_rejects_non_pdf_extension(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_wrong_mime_type(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("fake.pdf", b"hello", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_content_that_is_not_actually_a_pdf(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("fake.pdf", b"not a real pdf body", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    oversized = b"%PDF-1.4\n" + b"0" * (26 * 1024 * 1024)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("big.pdf", oversized, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_requires_owned_chat(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")
    chat_id = await _create_chat(client, alice)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=bob,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_requires_authentication(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_accepts_valid_pdf_and_enqueues_job(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert job_id

    job_response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "queued"

    documents = await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)
    assert documents.json()[0]["status"] == "pending"
    assert documents.json()[0]["filename"] == "doc.pdf"


@pytest.mark.asyncio
async def test_full_ingestion_pipeline_creates_searchable_chunks(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    user_id = await _current_user_id(client, headers)

    upload = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    job_id = upload.json()["job_id"]
    document_id = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)).json()[
        0
    ]["id"]

    await _run_worker(app, job_id, document_id, chat_id, user_id)

    job_response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_response.json()["status"] == "succeeded"
    assert job_response.json()["progress_stage"] == "complete"

    document_response = await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)
    document = document_response.json()[0]
    assert document["status"] == "ready"
    assert document["page_count"] == 1

    search_response = await client.post(
        f"/api/v1/chats/{chat_id}/search",
        json={"query": "What treats type 2 diabetes?"},
        headers=headers,
    )
    assert search_response.status_code == 200
    hits = search_response.json()
    assert len(hits) >= 1
    assert "Metformin" in hits[0]["text"]
    assert hits[0]["document_id"] == document_id


@pytest.mark.asyncio
async def test_ingestion_failure_marks_document_and_job_failed(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    """A file that passed upload validation (real PDF magic bytes + MIME) but
    is truncated/corrupt past the header must fail cleanly, not crash the
    worker or leave rows stuck in "processing" (CLAUDE.md §10)."""
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    user_id = await _current_user_id(client, headers)

    corrupt_pdf = b"%PDF-1.4\n" + b"garbage, not a real pdf body"
    upload = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", corrupt_pdf, "application/pdf")},
        headers=headers,
    )
    job_id = upload.json()["job_id"]
    document_id = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)).json()[
        0
    ]["id"]

    await _run_worker(app, job_id, document_id, chat_id, user_id)

    job_response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_response.json()["status"] == "failed"
    assert job_response.json()["error"]

    document_response = await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)
    assert document_response.json()[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_delete_document_removes_it(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    document_id = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)).json()[
        0
    ]["id"]

    response = await client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert response.status_code == 204

    documents_after = await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)
    assert documents_after.json() == []


@pytest.mark.asyncio
async def test_delete_document_not_owner_is_404(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")
    chat_id = await _create_chat(client, alice)
    await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", _make_pdf_bytes(), "application/pdf")},
        headers=alice,
    )
    document_id = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=alice)).json()[0][
        "id"
    ]

    response = await client.delete(f"/api/v1/documents/{document_id}", headers=bob)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_document_is_404(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.delete(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert response.status_code == 404
