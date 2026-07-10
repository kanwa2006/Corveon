"""Unit tests for claim extraction (app/evidence/claim_extraction.py),
against a stub ChatProvider — no real network/API key required, same
pattern the orchestrator's own tests use for the provider registry seam."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.evidence.claim_extraction import extract_claims
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


@pytest.mark.asyncio
async def test_extract_claims_parses_a_clean_json_array() -> None:
    registry = _registry('["Metformin is first-line therapy for type 2 diabetes."]')
    claims = await extract_claims(provider_registry=registry, text="irrelevant input")
    assert claims == ["Metformin is first-line therapy for type 2 diabetes."]


@pytest.mark.asyncio
async def test_extract_claims_strips_markdown_code_fences() -> None:
    registry = _registry('```json\n["Claim one.", "Claim two."]\n```')
    claims = await extract_claims(provider_registry=registry, text="irrelevant input")
    assert claims == ["Claim one.", "Claim two."]


@pytest.mark.asyncio
async def test_extract_claims_returns_empty_for_purely_conversational_text() -> None:
    registry = _registry("[]")
    claims = await extract_claims(provider_registry=registry, text="hi there!")
    assert claims == []


@pytest.mark.asyncio
async def test_extract_claims_falls_back_to_whole_text_on_malformed_json() -> None:
    registry = _registry("this is not json at all")
    claims = await extract_claims(provider_registry=registry, text="Aspirin thins the blood.")
    assert claims == ["Aspirin thins the blood."]


@pytest.mark.asyncio
async def test_extract_claims_falls_back_when_array_contains_non_strings() -> None:
    registry = _registry("[1, 2, 3]")
    claims = await extract_claims(provider_registry=registry, text="Some claim text.")
    assert claims == ["Some claim text."]


@pytest.mark.asyncio
async def test_extract_claims_returns_empty_for_blank_input_without_calling_provider() -> None:
    registry = _registry("should never be reached")
    claims = await extract_claims(provider_registry=registry, text="   ")
    assert claims == []


@pytest.mark.asyncio
async def test_extract_claims_respects_max_claims() -> None:
    registry = _registry('["a", "b", "c", "d", "e"]')
    claims = await extract_claims(provider_registry=registry, text="text", max_claims=2)
    assert claims == ["a", "b"]
