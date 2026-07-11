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
from app.data.models.medication import (
    DrugDataSnapshot,
    FindingSeverity,
    PipCriterion,
    PipDirection,
    PipSource,
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


async def _seed_pip_criterion(
    app,  # type: ignore[no-untyped-def]
    *,
    drug_name: str,
    condition_keywords: list[str] | None = None,
    direction: PipDirection = PipDirection.AVOID,
) -> None:
    async for session in app.state.db.session():
        snapshot = DrugDataSnapshot(
            source="beers_2023", version=f"test-{uuid.uuid4()}", checksum="test", row_count=1
        )
        session.add(snapshot)
        await session.flush()
        session.add(
            PipCriterion(
                snapshot_id=snapshot.id,
                source=PipSource.BEERS_2023,
                criterion_id=f"TEST-API-{uuid.uuid4()}",
                drug_names=[drug_name.strip().lower()],
                condition_keywords=condition_keywords or [],
                direction=direction,
                rationale="Anticholinergic burden increases fall and delirium risk.",
                recommendation="Consider a safer alternative.",
                severity=FindingSeverity.MAJOR,
            )
        )
        await session.commit()
        break


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
async def test_analyze_rejects_partial_renal_parameters(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    response = await client.post(
        f"/api/v1/chats/{chat_id}/medications/analyze",
        json={"raw_text": "apixaban 5mg", "age_years": 85, "weight_kg": 50},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"


@pytest.mark.asyncio
async def test_analyze_streams_a_renal_finding_when_renal_parameters_are_supplied(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            '[{"raw_text": "apixaban 5mg BID", "name": "apixaban", "dose": "5mg", '
            '"route": null, "frequency": "twice daily"}]'
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(
        RxNormMatch(rxcui="1364430", canonical_name="apixaban")
    )
    app.dependency_overrides[get_openfda_ddi_client] = lambda: _FakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={
                "raw_text": "apixaban 5mg BID",
                # Severely impaired renal function — both equations well
                # below apixaban's 30 mL/min threshold.
                "age_years": 85,
                "weight_kg": 50,
                "sex": "male",
                "serum_creatinine_mg_dl": 3.0,
                "height_cm": 170,
            },
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    renal_events = [json.loads(data) for kind, data in events if kind == "renal"]
    assert len(renal_events) == 1
    assert renal_events[0]["severity"] == "major"
    assert renal_events[0]["threshold_ml_min"] == 30.0
    assert renal_events[0]["crcl_ml_min"] < 30
    assert renal_events[0]["egfr_ml_min"] < 30


@pytest.mark.asyncio
async def test_analyze_emits_no_renal_events_when_renal_parameters_are_omitted(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)

    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            '[{"raw_text": "apixaban 5mg BID", "name": "apixaban", "dose": "5mg", '
            '"route": null, "frequency": "twice daily"}]'
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(
        RxNormMatch(rxcui="1364430", canonical_name="apixaban")
    )
    app.dependency_overrides[get_openfda_ddi_client] = lambda: _FakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={"raw_text": "apixaban 5mg BID"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    renal_events = [json.loads(data) for kind, data in events if kind == "renal"]
    assert renal_events == []
    done_events = [json.loads(data) for kind, data in events if kind == "done"]
    assert len(done_events) == 1


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


@pytest.mark.asyncio
async def test_analyze_streams_a_pip_finding_when_age_years_is_supplied(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    drug = f"beers-drug-{uuid.uuid4()}"
    await _seed_pip_criterion(app, drug_name=drug)

    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            f'[{{"raw_text": "{drug} 25mg", "name": "{drug}", "dose": "25mg", '
            '"route": null, "frequency": null}]',
            # One batched narrative-generation call follows the PIP finding
            # (ADR-0020) — a single-element array, no narrative text
            # asserted on below since that behavior is unit-tested
            # separately (test_medication_explanation_guardrail.py).
            '["A plain-language note."]',
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(None)
    app.dependency_overrides[get_openfda_ddi_client] = lambda: _FakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={"raw_text": f"{drug} 25mg", "age_years": 78},
            headers=headers,
        ) as response:
            assert response.status_code == 202
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    pip_events = [json.loads(data) for kind, data in events if kind == "pip"]
    assert len(pip_events) == 1
    assert pip_events[0]["source"] == "beers_2023"
    assert pip_events[0]["direction"] == "avoid"
    assert pip_events[0]["severity"] == "major"
    assert pip_events[0]["medication_id"] is not None
    assert pip_events[0]["narrative"] is None or isinstance(pip_events[0]["narrative"], str)
    done_events = [json.loads(data) for kind, data in events if kind == "done"]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_analyze_emits_no_pip_events_when_age_years_is_omitted(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    drug = f"beers-drug-{uuid.uuid4()}"
    await _seed_pip_criterion(app, drug_name=drug)

    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            f'[{{"raw_text": "{drug} 25mg", "name": "{drug}", "dose": "25mg", '
            '"route": null, "frequency": null}]'
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(None)
    app.dependency_overrides[get_openfda_ddi_client] = lambda: _FakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={"raw_text": f"{drug} 25mg"},
            headers=headers,
        ) as response:
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    assert [json.loads(data) for kind, data in events if kind == "pip"] == []


@pytest.mark.asyncio
async def test_analyze_streams_discrepancy_findings_when_previous_raw_text_is_supplied(
    client: AsyncClient, auth_headers: AuthHeaders, app
) -> None:
    headers = await auth_headers("alice@example.com")
    chat_id = await _create_chat(client, headers)
    current_drug = f"current-drug-{uuid.uuid4()}"
    previous_drug = f"previous-drug-{uuid.uuid4()}"

    app.dependency_overrides[get_provider_registry] = lambda: _provider_registry(
        [
            f'[{{"raw_text": "{current_drug}", "name": "{current_drug}", "dose": null, '
            '"route": null, "frequency": null}]',
            f'[{{"raw_text": "{previous_drug}", "name": "{previous_drug}", "dose": null, '
            '"route": null, "frequency": null}]',
            # Batched narrative call covering both discrepancy findings.
            '["Added note.", "Omitted note."]',
        ]
    )
    app.dependency_overrides[get_rxnorm_client] = lambda: _FakeRxNormClient(None)
    app.dependency_overrides[get_openfda_ddi_client] = lambda: _FakeOpenFdaDdiClient()
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/medications/analyze",
            json={"raw_text": current_drug, "previous_raw_text": previous_drug},
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
    previous_medication_events = [
        json.loads(data) for kind, data in events if kind == "previous_medication"
    ]
    assert len(medication_events) == 1
    assert len(previous_medication_events) == 1

    discrepancy_events = [json.loads(data) for kind, data in events if kind == "discrepancy"]
    kinds = {event["kind"] for event in discrepancy_events}
    assert kinds == {"added", "omitted"}
    added_event = next(event for event in discrepancy_events if event["kind"] == "added")
    assert added_event["current_medication_id"] == medication_events[0]["id"]
    assert added_event["previous_medication_id"] is None
    omitted_event = next(event for event in discrepancy_events if event["kind"] == "omitted")
    assert omitted_event["previous_medication_id"] == previous_medication_events[0]["id"]
    assert omitted_event["current_medication_id"] is None


@pytest.mark.asyncio
async def test_analyze_emits_no_discrepancy_events_when_previous_raw_text_is_omitted(
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
            raw = await response.aread()
    finally:
        app.dependency_overrides.pop(get_provider_registry, None)
        app.dependency_overrides.pop(get_rxnorm_client, None)
        app.dependency_overrides.pop(get_openfda_ddi_client, None)

    events = _parse_sse(raw.decode())
    assert [json.loads(data) for kind, data in events if kind == "discrepancy"] == []
    assert [json.loads(data) for kind, data in events if kind == "previous_medication"] == []
