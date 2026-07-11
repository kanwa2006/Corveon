"""API tests: SSE-streaming grounded chat (docs/API.md — Messages/AI).

A stub ChatProvider is injected via FastAPI's dependency_overrides for the
happy-path tests (no real Gemini/Ollama network calls or API keys). The
degraded-mode test deliberately uses no override — the default test
environment has no Gemini key and no reachable Ollama, so it exercises the
real "no provider available" path (ADR-0006), not a simulation of it."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import fitz
import pytest
from app.api.deps import get_evidence_connector_registry, get_provider_registry
from app.core.config import get_settings
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry
from app.ingestion.embeddings import get_embedding_model
from app.providers.base import ChatMessage, ChatProvider
from app.providers.registry import ProviderRegistry
from app.workers.tasks import run_ingestion
from httpx import AsyncClient

pytestmark = pytest.mark.api

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


class _StubProvider(ChatProvider):
    name = "stub"

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        for delta in self._deltas:
            yield delta


class _FakeEvidenceConnector:
    def __init__(self, name: EvidenceSourceName, results: list[EvidenceResult]) -> None:
        self.name = name
        self._results = results

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        return self._results[:limit]


def _empty_evidence_registry() -> EvidenceConnectorRegistry:
    return EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: _FakeEvidenceConnector(EvidenceSourceName.PUBMED, [])}
    )


def _pubmed_evidence_registry() -> EvidenceConnectorRegistry:
    result = EvidenceResult(
        source=EvidenceSourceName.PUBMED,
        title="Headache management: a review",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        identifier="12345678",
        snippet="NSAIDs are first-line therapy for tension-type headache.",
        published_date=None,
    )
    return EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: _FakeEvidenceConnector(EvidenceSourceName.PUBMED, [result])}
    )


def _parse_sse(raw_text: str) -> list[tuple[str, str]]:
    # SSE line endings may be \r\n (sse-starlette's default); normalize
    # before splitting on the blank-line record separator.
    normalized = raw_text.replace("\r\n", "\n")
    events: list[tuple[str, str]] = []
    for block in normalized.strip().split("\n\n"):
        event_type = "message"
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                # Per the SSE spec, only the single mandatory space after
                # "data:" is stripped — a leading space in the value itself
                # (e.g. a token delta continuing a word) is meaningful.
                data_lines.append(line.removeprefix("data:").removeprefix(" "))
        if data_lines:
            events.append((event_type, "\n".join(data_lines)))
    return events


async def _create_chat(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/v1/chats", json={"title": "Chat"}, headers=headers)
    chat_id: str = response.json()["id"]
    return chat_id


@pytest.mark.asyncio
async def test_send_message_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages", json={"content": "hi"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_message_requires_owned_chat(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/messages",
        json={"content": "hi"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_streams_and_persists_assistant_reply(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider(["Hello", " there"])}, ["stub"]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "hi"},
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)

    events = _parse_sse(raw.decode())
    token_events = [data for kind, data in events if kind == "token"]
    assert token_events == ["Hello", " there"]

    done_events = [json.loads(data) for kind, data in events if kind == "done"]
    assert len(done_events) == 1
    assert done_events[0]["routing_trace"]["status"] == "ok"
    assert done_events[0]["routing_trace"]["path"] == "fast_path"
    assert done_events[0]["routing_trace"]["provider"] == "stub"

    history = (await client.get(f"/api/v1/chats/{chat_id}/messages", headers=headers)).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "hi"
    assert history[1]["content"] == "Hello there"


@pytest.mark.asyncio
async def test_send_message_degrades_gracefully_with_no_provider_reachable(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    async with client.stream(
        "POST", f"/api/v1/chats/{chat_id}/messages", json={"content": "hi"}, headers=headers
    ) as response:
        assert response.status_code == 202
        raw = await response.aread()

    events = _parse_sse(raw.decode())
    error_events = [json.loads(data) for kind, data in events if kind == "error"]
    assert len(error_events) == 1
    assert error_events[0]["error_code"] == "provider_unavailable"

    history = (await client.get(f"/api/v1/chats/{chat_id}/messages", headers=headers)).json()
    assert history[-1]["role"] == "assistant"
    assert history[-1]["routing_trace"]["status"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_send_message_grounds_answer_in_uploaded_document(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    user_id = (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Metformin is a first-line treatment for type 2 diabetes.")
    pdf_bytes = doc.tobytes()
    doc.close()

    upload = await client.post(
        f"/api/v1/chats/{chat_id}/documents",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    job_id = upload.json()["job_id"]
    document_id = (await client.get(f"/api/v1/chats/{chat_id}/documents", headers=headers)).json()[
        0
    ]["id"]

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

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider(["Grounded answer."])}, ["stub"]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "What treats type 2 diabetes?"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)

    done_event = next(json.loads(data) for kind, data in _parse_sse(raw.decode()) if kind == "done")
    assert done_event["routing_trace"]["path"] == "rag_grounded"
    assert len(done_event["routing_trace"]["retrieved_chunks"]) >= 1
    assert done_event["routing_trace"]["retrieved_chunks"][0]["document_filename"] == "doc.pdf"


@pytest.mark.asyncio
async def test_send_message_grounds_answer_in_public_evidence_when_no_documents(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    """ADR-0021: a substantive query in a chat with no uploaded documents
    searches public evidence sources instead of falling straight through
    to an ungrounded pure-LLM answer."""
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider(["Grounded in public evidence."])}, ["stub"]
    )
    app.dependency_overrides[get_evidence_connector_registry] = _pubmed_evidence_registry
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "What treats a headache?"},
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_evidence_connector_registry, None)

    done_event = next(json.loads(data) for kind, data in _parse_sse(raw.decode()) if kind == "done")
    assert done_event["routing_trace"]["path"] == "rag_public_evidence"
    assert done_event["routing_trace"]["retrieved_chunks"] == []
    public_evidence = done_event["routing_trace"]["public_evidence"]
    assert len(public_evidence) == 1
    assert public_evidence[0]["source"] == "pubmed"
    assert public_evidence[0]["title"] == "Headache management: a review"


@pytest.mark.asyncio
async def test_send_message_uses_pure_llm_when_no_documents_and_no_public_evidence_found(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider(["An ungrounded answer."])}, ["stub"]
    )
    app.dependency_overrides[get_evidence_connector_registry] = _empty_evidence_registry
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "What treats a headache?"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_evidence_connector_registry, None)

    done_event = next(json.loads(data) for kind, data in _parse_sse(raw.decode()) if kind == "done")
    assert done_event["routing_trace"]["path"] == "pure_llm"
    assert done_event["routing_trace"]["public_evidence"] == []


@pytest.mark.asyncio
async def test_export_message_as_markdown(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider(["Grounded answer."])}, ["stub"]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "hi"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
    done_event = next(json.loads(data) for kind, data in _parse_sse(raw.decode()) if kind == "done")
    message_id = done_event["message_id"]

    export_response = await client.post(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/export",
        json={"format": "md"},
        headers=headers,
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in export_response.headers["content-disposition"]
    assert b"Grounded answer." in export_response.content


@pytest.mark.asyncio
async def test_export_message_as_pdf(client: AsyncClient, auth_headers: AuthHeaders, app) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _StubProvider(["Grounded answer."])}, ["stub"]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "hi"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
    done_event = next(json.loads(data) for kind, data in _parse_sse(raw.decode()) if kind == "done")
    message_id = done_event["message_id"]

    export_response = await client.post(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/export",
        json={"format": "pdf"},
        headers=headers,
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/pdf"
    assert export_response.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_export_message_requires_owned_chat(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")
    chat_id = await _create_chat(client, alice)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/messages/00000000-0000-0000-0000-000000000000/export",
        json={"format": "md"},
        headers=bob,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_nonexistent_message_is_404(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/messages/00000000-0000-0000-0000-000000000000/export",
        json={"format": "md"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_message_requires_authentication(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/messages/00000000-0000-0000-0000-000000000000/export",
        json={"format": "md"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_messages_requires_owned_chat(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    alice = await auth_headers("alice@example.com")
    bob = await auth_headers("bob@example.com")
    chat_id = await _create_chat(client, alice)

    response = await client.get(f"/api/v1/chats/{chat_id}/messages", headers=bob)
    assert response.status_code == 404
