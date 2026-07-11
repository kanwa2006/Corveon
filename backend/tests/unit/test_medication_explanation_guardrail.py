"""Unit tests for the guardrailed LLM explanation narrative
(app/medication/explanation_guardrail.py, ADR-0020): the deterministic
grounding check on its own, then the batched generation call against a stub
provider (same pattern as test_medication_normalizer.py) — no live LLM."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from app.medication.explanation_guardrail import (
    NarrativeFact,
    check_narrative_grounded,
    generate_grounded_narratives,
)
from app.providers.base import ChatMessage, ChatProvider
from app.providers.budget import LLMCallBudget
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


def _fact(**overrides: object) -> NarrativeFact:
    defaults: dict[str, object] = {
        "key": "pip:0",
        "drug_names": ["diphenhydramine"],
        "severity": "major",
        "rationale": "Anticholinergic burden increases fall and delirium risk in older adults.",
        "recommendation": "Avoid; consider a non-anticholinergic alternative.",
        "explanation": (
            "AGS Beers Criteria 2023: avoid diphenhydramine — anticholinergic burden "
            "increases fall and delirium risk. Avoid; consider a non-anticholinergic "
            "alternative."
        ),
    }
    defaults.update(overrides)
    return NarrativeFact(**defaults)  # type: ignore[arg-type]


# ── check_narrative_grounded ────────────────────────────────────────────


def test_check_narrative_grounded_passes_a_narrative_that_only_restates_given_facts() -> None:
    fact = _fact()
    narrative = (
        "Diphenhydramine is a Beers Criteria drug to avoid in older adults because of its "
        "anticholinergic burden and fall/delirium risk."
    )
    assert check_narrative_grounded(
        narrative,
        allowed_text=" ".join([fact.rationale, fact.recommendation, fact.explanation]),
        other_drug_names=set(),
    )


def test_check_narrative_grounded_fails_on_a_medication_name_outside_this_finding() -> None:
    fact = _fact()
    narrative = "Diphenhydramine interacts badly with warfarin, avoid combining them."
    assert not check_narrative_grounded(
        narrative,
        allowed_text=" ".join([fact.rationale, fact.recommendation, fact.explanation]),
        other_drug_names={"warfarin"},
    )


def test_check_narrative_grounded_fails_on_an_invented_number() -> None:
    fact = _fact()
    narrative = "Reduce the dose by 50% due to anticholinergic burden."
    assert not check_narrative_grounded(
        narrative,
        allowed_text=" ".join([fact.rationale, fact.recommendation, fact.explanation]),
        other_drug_names=set(),
    )


def test_check_narrative_grounded_fails_on_an_escalation_word_not_in_the_source() -> None:
    fact = _fact()
    narrative = "This is a severe and life-threatening combination."
    assert not check_narrative_grounded(
        narrative,
        allowed_text=" ".join([fact.rationale, fact.recommendation, fact.explanation]),
        other_drug_names=set(),
    )


def test_check_narrative_grounded_fails_on_an_unlicensed_directive_phrase() -> None:
    fact = _fact()
    narrative = "Stop taking this medication immediately and switch to a different drug."
    assert not check_narrative_grounded(
        narrative,
        allowed_text=" ".join([fact.rationale, fact.recommendation, fact.explanation]),
        other_drug_names=set(),
    )


def test_check_narrative_grounded_allows_a_directive_phrase_already_in_the_source() -> None:
    fact = _fact(
        recommendation="Avoid; consider a non-anticholinergic alternative.",
        explanation="... Avoid; consider a non-anticholinergic alternative.",
    )
    narrative = "Avoid this drug; consider a non-anticholinergic alternative instead."
    assert check_narrative_grounded(
        narrative,
        allowed_text=" ".join([fact.rationale, fact.recommendation, fact.explanation]),
        other_drug_names=set(),
    )


# ── generate_grounded_narratives ────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_grounded_narratives_returns_empty_dict_for_no_facts() -> None:
    result = await generate_grounded_narratives(
        [],
        all_drug_names=set(),
        provider_registry=_registry("should never be read"),
        budget=LLMCallBudget(5),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_generate_grounded_narratives_pairs_grounded_narratives_by_key() -> None:
    fact = _fact()
    response = json.dumps(
        ["Diphenhydramine is a Beers Criteria drug to avoid due to anticholinergic burden."]
    )
    result = await generate_grounded_narratives(
        [fact],
        all_drug_names={"diphenhydramine"},
        provider_registry=_registry(response),
        budget=LLMCallBudget(5),
    )
    assert set(result.keys()) == {"pip:0"}


@pytest.mark.asyncio
async def test_generate_grounded_narratives_drops_an_ungrounded_narrative() -> None:
    fact = _fact()
    response = json.dumps(["This severe interaction with warfarin requires stopping the drug."])
    result = await generate_grounded_narratives(
        [fact],
        all_drug_names={"diphenhydramine", "warfarin"},
        provider_registry=_registry(response),
        budget=LLMCallBudget(5),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_generate_grounded_narratives_degrades_to_empty_dict_on_malformed_json() -> None:
    result = await generate_grounded_narratives(
        [_fact()],
        all_drug_names={"diphenhydramine"},
        provider_registry=_registry("not json at all"),
        budget=LLMCallBudget(5),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_generate_grounded_narratives_degrades_to_empty_dict_on_wrong_length_array() -> None:
    result = await generate_grounded_narratives(
        [_fact(), _fact(key="pip:1")],
        all_drug_names={"diphenhydramine"},
        provider_registry=_registry(json.dumps(["only one narrative"])),
        budget=LLMCallBudget(5),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_generate_grounded_narratives_degrades_to_empty_dict_when_no_provider_available() -> (
    None
):
    empty_registry = ProviderRegistry({}, [])
    result = await generate_grounded_narratives(
        [_fact()],
        all_drug_names={"diphenhydramine"},
        provider_registry=empty_registry,
        budget=LLMCallBudget(5),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_generate_grounded_narratives_degrades_to_empty_dict_when_budget_exhausted() -> None:
    budget = LLMCallBudget(0)
    result = await generate_grounded_narratives(
        [_fact()],
        all_drug_names={"diphenhydramine"},
        provider_registry=_registry(json.dumps(["irrelevant"])),
        budget=budget,
    )
    assert result == {}
