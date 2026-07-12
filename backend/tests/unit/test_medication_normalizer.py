"""Unit tests for app/medication/normalizer.py: free-text parsing (stub
ChatProvider, same pattern as test_evidence_claim_extraction.py) and RxCUI
normalization (fake RxNormClient, no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.medication.normalizer import (
    ParsedMedicationEntry,
    normalize_entry,
    parse_medication_entries,
)
from app.medication.rxnorm_client import RxNormMatch
from app.providers.base import ChatMessage, ChatProvider
from app.providers.registry import ProviderRegistry

pytestmark = pytest.mark.unit


class _StubProvider(ChatProvider):
    name = "stub"

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        yield self._response_text


def _registry(response_text: str) -> ProviderRegistry:
    return ProviderRegistry({"stub": _StubProvider(response_text)}, ["stub"])


# ── parse_medication_entries ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_medication_entries_parses_a_clean_json_array() -> None:
    registry = _registry(
        '[{"raw_text": "metformin 500mg BID", "name": "metformin", "dose": "500mg", '
        '"route": null, "frequency": "twice daily"}]'
    )
    entries = await parse_medication_entries(provider_registry=registry, text="irrelevant input")

    assert entries == [
        ParsedMedicationEntry(
            raw_text="metformin 500mg BID",
            name="metformin",
            dose="500mg",
            route=None,
            frequency="twice daily",
        )
    ]


@pytest.mark.asyncio
async def test_parse_medication_entries_strips_markdown_code_fences() -> None:
    registry = _registry(
        '```json\n[{"raw_text": "aspirin", "name": "aspirin", "dose": null, '
        '"route": null, "frequency": null}]\n```'
    )
    entries = await parse_medication_entries(provider_registry=registry, text="irrelevant input")
    assert entries[0].name == "aspirin"


@pytest.mark.asyncio
async def test_parse_medication_entries_falls_back_to_whole_text_on_malformed_json() -> None:
    registry = _registry("this is not json at all")
    entries = await parse_medication_entries(
        provider_registry=registry, text="lisinopril 10mg daily"
    )
    assert entries == [
        ParsedMedicationEntry(
            raw_text="lisinopril 10mg daily",
            name="lisinopril 10mg daily",
            dose=None,
            route=None,
            frequency=None,
        )
    ]


@pytest.mark.asyncio
async def test_parse_medication_entries_falls_back_when_entry_missing_name() -> None:
    registry = _registry('[{"raw_text": "something", "dose": "5mg"}]')
    entries = await parse_medication_entries(provider_registry=registry, text="something 5mg")
    assert entries == [
        ParsedMedicationEntry(
            raw_text="something 5mg", name="something 5mg", dose=None, route=None, frequency=None
        )
    ]


@pytest.mark.asyncio
async def test_parse_medication_entries_returns_empty_for_blank_input() -> None:
    registry = _registry("should never be reached")
    entries = await parse_medication_entries(provider_registry=registry, text="   ")
    assert entries == []


@pytest.mark.asyncio
async def test_parse_medication_entries_respects_max_entries() -> None:
    items = ", ".join(
        f'{{"raw_text": "drug{i}", "name": "drug{i}", "dose": null, '
        f'"route": null, "frequency": null}}'
        for i in range(30)
    )
    registry = _registry(f"[{items}]")
    entries = await parse_medication_entries(provider_registry=registry, text="a long list")
    assert len(entries) == 25


# ── normalize_entry ──────────────────────────────────────────────────────


class _FakeRxNormClient:
    def __init__(self, match: RxNormMatch | None) -> None:
        self._match = match
        self.queries: list[str] = []

    async def normalize(self, name: str) -> RxNormMatch | None:
        self.queries.append(name)
        return self._match


@pytest.mark.asyncio
async def test_normalize_entry_returns_rxcui_and_canonical_name_on_match() -> None:
    entry = ParsedMedicationEntry(
        raw_text="metformin", name="metformin", dose=None, route=None, frequency=None
    )
    fake_client = _FakeRxNormClient(RxNormMatch(rxcui="6809", canonical_name="Metformin"))

    rxcui, name, match_names = await normalize_entry(entry, rxnorm_client=fake_client)

    assert rxcui == "6809"
    assert name == "Metformin"
    assert match_names == ("metformin",)
    assert fake_client.queries == ["metformin"]


@pytest.mark.asyncio
async def test_normalize_entry_falls_back_to_parsed_name_when_unmatched() -> None:
    entry = ParsedMedicationEntry(
        raw_text="some made up drug",
        name="some made up drug",
        dose=None,
        route=None,
        frequency=None,
    )
    fake_client = _FakeRxNormClient(None)

    rxcui, name, match_names = await normalize_entry(entry, rxnorm_client=fake_client)

    assert rxcui is None
    assert name == "some made up drug"
    assert match_names == ("some made up drug",)


@pytest.mark.asyncio
async def test_normalize_entry_match_names_use_ingredients_not_the_branded_display_name() -> None:
    """Regression (N1): RxNav's canonical name is often a verbose branded
    product string ("apixaban 5 MG Oral Tablet [Eliquis]") that the
    ingredient-keyed rules engines can never match — match_names must carry
    the IN/MIN ingredient names plus the user's parsed name, and never the
    branded display string."""
    entry = ParsedMedicationEntry(
        raw_text="Eliquis 5mg BID", name="Eliquis", dose="5mg", route=None, frequency=None
    )
    fake_client = _FakeRxNormClient(
        RxNormMatch(
            rxcui="562282",
            canonical_name="apixaban 5 MG Oral Tablet [Eliquis]",
            ingredient_names=("apixaban",),
        )
    )

    rxcui, name, match_names = await normalize_entry(entry, rxnorm_client=fake_client)

    assert rxcui == "562282"
    assert name == "apixaban 5 MG Oral Tablet [Eliquis]"
    assert match_names == ("apixaban", "eliquis")
