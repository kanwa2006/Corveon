"""API tests: Medication-Safety Engine endpoint (docs/API.md — Evidence &
medication). Stub ChatProvider + fake RxNorm/openFDA clients are injected
via FastAPI's dependency_overrides, mirroring test_evidence_api.py's
pattern — no real LLM/network calls required."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from app.api.deps import (
    get_openfda_ddi_client,
    get_provider_registry,
    get_rxnorm_client,
)
from app.medication.openfda_ddi_client import OpenFdaDdiMatch
from app.medication.rxnorm_client import RxNormMatch
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


def _provider_registry(responses: list[str]) -> ProviderRegistry:
    return ProviderRegistry({"stub": _ScriptedProvider(responses)}, ["stub"])


class _FakeRxNormClient:
    def __init__(self, match: RxNormMatch | None) -> None:
        self._match = match

    async def normalize(self, name: str) -> RxNormMatch | None:
        return self._match


class _FakeOpenFdaDdiClient:
    async def check_pair(self, label_drug: str, mentioned_drug: str) -> None:
        return None


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


@pytest.mark.asyncio
async def test_analyze_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/medications/analyze",
        json={"raw_text": "metformin 500mg"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_analyze_requires_owned_chat(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers("alice@example.com")
    response = await client.post(
        "/api/v1/chats/00000000-0000-0000-0000-000000000000/medications/analyze",
        json={"raw_text": "metformin 500mg"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analyze_rejects_empty_raw_text(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/medications/analyze",
        json={"raw_text": ""},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_rejects_nul_byte_in_raw_text(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/medications/analyze",
        json={"raw_text": "metformin\x00500mg"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_analyze_streams_normalized_medications(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            '[{"raw_text": "metformin 500mg BID", "name": "metformin", "dose": "500mg", '
            '"route": null, "frequency": "twice daily"}]'
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(
        RxNormMatch(rxcui="6809", canonical_name="Metformin")
    )
    app.dependency_overrides[get_openfda_ddi_client] = lambda: _FakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={"raw_text": "metformin 500mg BID"},
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    medication_events = [json.loads(data) for kind, data in events if kind == "medication"]
    assert len(medication_events) == 1
    assert medication_events[0]["name"] == "Metformin"
    assert medication_events[0]["rxcui"] == "6809"

    done_events = [json.loads(data) for kind, data in events if kind == "done"]
    assert len(done_events) == 1
    assert done_events[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_analyze_streams_an_interaction_finding_from_openfda_fallback(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    # drug_data_snapshots/drug_interactions are shared reference data, not
    # truncated between tests — unique fake names guarantee DDInter has no
    # record, so this actually exercises the openFDA fallback path.
    drug_a, drug_b = f"drug-a-{uuid.uuid4()}", f"drug-b-{uuid.uuid4()}"
    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            json.dumps(
                [
                    {
                        "raw_text": drug_a,
                        "name": drug_a,
                        "dose": None,
                        "route": None,
                        "frequency": None,
                    },
                    {
                        "raw_text": drug_b,
                        "name": drug_b,
                        "dose": None,
                        "route": None,
                        "frequency": None,
                    },
                ]
            )
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(None)

    class _MatchingFakeOpenFdaDdiClient:
        async def check_pair(self, label_drug: str, mentioned_drug: str) -> OpenFdaDdiMatch | None:
            return OpenFdaDdiMatch(
                label_id="label-xyz",
                url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=label-xyz",
                snippet="Increases bleeding risk.",
            )

    app.dependency_overrides[get_openfda_ddi_client] = lambda: _MatchingFakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={"raw_text": f"{drug_a} and {drug_b}"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    interaction_events = [json.loads(data) for kind, data in events if kind == "interaction"]
    assert len(interaction_events) == 1
    assert interaction_events[0]["source"] == "openfda_label"
    assert interaction_events[0]["severity"] == "unclassified"
    assert interaction_events[0]["rule_id"] == "label-xyz"


@pytest.mark.asyncio
async def test_analyze_degrades_gracefully_with_no_provider_reachable(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    async with client.stream(
        "POST",
        f"/api/v1/chats/{chat_id}/medications/analyze",
        json={"raw_text": "metformin 500mg"},
        headers=headers,
    ) as response:
        assert response.status_code == 202
        raw = await response.aread()

    events = _parse_sse(raw.decode())
    error_events = [json.loads(data) for kind, data in events if kind == "error"]
    assert len(error_events) == 1
    assert error_events[0]["error_code"] == "provider_unavailable"
