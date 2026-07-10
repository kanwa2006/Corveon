"""API tests: Evidence Verification endpoint (docs/API.md — Evidence
verification). Stub ChatProvider + fake evidence connectors are injected via
FastAPI's dependency_overrides, mirroring test_messages_api.py's pattern —
no real LLM/network calls required."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from app.api.deps import get_evidence_connector_registry, get_provider_registry
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry
from app.providers.base import ChatMessage, ChatProvider
from app.providers.registry import ProviderRegistry
from httpx import AsyncClient

pytestmark = pytest.mark.api

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


class _ScriptedProvider(ChatProvider):
    name = "stub"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        yield self._responses.pop(0)


class _FakeConnector:
    def __init__(self, name: EvidenceSourceName, results: list[EvidenceResult]) -> None:
        self.name = name
        self._results = results

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        return self._results[:limit]


def _empty_connector_registry() -> EvidenceConnectorRegistry:
    return EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: _FakeConnector(EvidenceSourceName.PUBMED, [])}
    )


def _pubmed_connector_registry() -> EvidenceConnectorRegistry:
    result = EvidenceResult(
        source=EvidenceSourceName.PUBMED,
        title="A study",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        identifier="12345678",
        snippet="Metformin is first-line therapy for type 2 diabetes.",
        published_date=None,
    )
    return EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: _FakeConnector(EvidenceSourceName.PUBMED, [result])}
    )


def _parse_sse(raw_text: str) -> list[tuple[str, str]]:
    normalized = raw_text.replace("\r\n", "\n")
    events: list[tuple[str, str]] = []
    for block in normalized.strip().split("\n\n"):
        event_type = "message"
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").removeprefix(" "))
        if data_lines:
            events.append((event_type, "\n".join(data_lines)))
    return events


async def _create_chat(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/v1/chats", json={"title": "Chat"}, headers=headers)
    chat_id: str = response.json()["id"]
    return chat_id


async def _send_message(
    client: AsyncClient, app, headers: dict[str, str], chat_id: str, content: str
) -> str:
    """Sends a user message via the real messages endpoint (a provider
    override is needed so it doesn't degrade) and returns the persisted
    user message's id — the natural target of a verify request."""
    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {"stub": _ScriptedProvider(["An answer."])}, ["stub"]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": content},
            headers=headers,
        ) as response:
            await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)

    history = (await client.get(f"/api/v1/chats/{chat_id}/messages", headers=headers)).json()
    user_message_id: str = next(m["id"] for m in history if m["role"] == "user")
    return user_message_id


@pytest.mark.asyncio
async def test_verify_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/verify",
        json={"message_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_requires_owned_chat(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/verify",
        json={"message_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_verify_returns_404_for_nonexistent_message(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/verify",
        json={"message_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_verify_streams_a_claim_and_done_event(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    message_id = await _send_message(
        client, app, headers, chat_id, "Metformin is first-line therapy for type 2 diabetes."
    )

    app.dependency_overrides[get_provider_registry] = lambda: ProviderRegistry(
        {
            "stub": _ScriptedProvider(
                [
                    '["Metformin is first-line therapy for type 2 diabetes."]',
                    '{"stances": ["supports"], "flags": []}',
                ]
            )
        },
        ["stub"],
    )
    app.dependency_overrides[get_evidence_connector_registry] = _pubmed_connector_registry
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/verify",
            json={"message_id": message_id},
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_evidence_connector_registry, None)

    events = _parse_sse(raw.decode())
    claim_events = [json.loads(data) for kind, data in events if kind == "claim"]
    assert len(claim_events) == 1
    assert claim_events[0]["source_class"] == "verified_public"
    assert len(claim_events[0]["citations"]) == 1
    assert claim_events[0]["citations"][0]["source"] == "pubmed"

    done_events = [json.loads(data) for kind, data in events if kind == "done"]
    assert len(done_events) == 1
    assert done_events[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_verify_degrades_gracefully_with_no_provider_reachable(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    message_id = await _send_message(client, app, headers, chat_id, "hi")

    app.dependency_overrides[get_evidence_connector_registry] = _empty_connector_registry
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/verify",
            json={"message_id": message_id},
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_evidence_connector_registry, None)

    events = _parse_sse(raw.decode())
    error_events = [json.loads(data) for kind, data in events if kind == "error"]
    assert len(error_events) == 1
    assert error_events[0]["error_code"] == "provider_unavailable"
