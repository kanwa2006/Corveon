"""Unit tests for per-claim evidence analysis (app/evidence/analysis.py),
against a stub ChatProvider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.analysis import Stance, analyze_claim
from app.evidence.connectors.base import EvidenceResult
from app.providers.base import ChatMessage, ChatProvider
from app.providers.registry import ProviderRegistry

pytestmark = pytest.mark.unit


class _StubProvider(ChatProvider):
    name = "stub"

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.call_count = 0

    async def stream_chat(
        self, *, messages: list[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        self.call_count += 1
        yield self._response_text


def _evidence(source: EvidenceSourceName, title: str) -> EvidenceResult:
    return EvidenceResult(
        source=source,
        title=title,
        url=None,
        identifier=None,
        snippet=None,
        published_date=date(2024, 1, 1),
    )


@pytest.mark.asyncio
async def test_analyze_claim_skips_provider_call_when_no_evidence() -> None:
    provider = _StubProvider("should never be reached")
    registry = ProviderRegistry({"stub": provider}, ["stub"])

    result = await analyze_claim(provider_registry=registry, claim_text="A claim.", evidence=[])

    assert result.stances == []
    assert result.flags == [
        {"type": "unsupported", "detail": "No evidence was found from any configured source."}
    ]
    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_analyze_claim_parses_stances_and_flags() -> None:
    provider = _StubProvider(
        '{"stances": ["supports", "contradicts"], '
        '"flags": [{"type": "contradictory", "detail": "Sources disagree."}]}'
    )
    registry = ProviderRegistry({"stub": provider}, ["stub"])
    evidence = [
        _evidence(EvidenceSourceName.PUBMED, "Study A"),
        _evidence(EvidenceSourceName.DAILYMED, "Label B"),
    ]

    result = await analyze_claim(
        provider_registry=registry, claim_text="A claim.", evidence=evidence
    )

    assert result.stances == [Stance.SUPPORTS, Stance.CONTRADICTS]
    assert result.flags == [{"type": "contradictory", "detail": "Sources disagree."}]


@pytest.mark.asyncio
async def test_analyze_claim_falls_back_to_irrelevant_on_malformed_json() -> None:
    provider = _StubProvider("not json")
    registry = ProviderRegistry({"stub": provider}, ["stub"])
    evidence = [_evidence(EvidenceSourceName.PUBMED, "Study A")]

    result = await analyze_claim(
        provider_registry=registry, claim_text="A claim.", evidence=evidence
    )

    assert result.stances == [Stance.IRRELEVANT]
    assert result.flags[0]["type"] == "unsupported"


@pytest.mark.asyncio
async def test_analyze_claim_falls_back_when_stance_count_mismatches_evidence_count() -> None:
    provider = _StubProvider('{"stances": ["supports"], "flags": []}')
    registry = ProviderRegistry({"stub": provider}, ["stub"])
    evidence = [
        _evidence(EvidenceSourceName.PUBMED, "Study A"),
        _evidence(EvidenceSourceName.DAILYMED, "Label B"),
    ]

    result = await analyze_claim(
        provider_registry=registry, claim_text="A claim.", evidence=evidence
    )

    assert result.stances == [Stance.IRRELEVANT, Stance.IRRELEVANT]


@pytest.mark.asyncio
async def test_analyze_claim_falls_back_on_an_invalid_stance_value() -> None:
    provider = _StubProvider('{"stances": ["maybe"], "flags": []}')
    registry = ProviderRegistry({"stub": provider}, ["stub"])
    evidence = [_evidence(EvidenceSourceName.PUBMED, "Study A")]

    result = await analyze_claim(
        provider_registry=registry, claim_text="A claim.", evidence=evidence
    )

    assert result.stances == [Stance.IRRELEVANT]


@pytest.mark.asyncio
async def test_analyze_claim_strips_markdown_code_fences() -> None:
    provider = _StubProvider('```json\n{"stances": ["supports"], "flags": []}\n```')
    registry = ProviderRegistry({"stub": provider}, ["stub"])
    evidence = [_evidence(EvidenceSourceName.MESH, "Concept")]

    result = await analyze_claim(
        provider_registry=registry, claim_text="A claim.", evidence=evidence
    )

    assert result.stances == [Stance.SUPPORTS]
