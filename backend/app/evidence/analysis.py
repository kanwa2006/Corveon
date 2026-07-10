"""Per-claim evidence analysis (blueprint §8: contradiction/outdatedness/
unsupported-claim detection, conflict surfacing). One LLM call per claim —
not per citation — comparing the claim against every retrieved excerpt at
once, so a verification request with several claims stays within the
existing per-request LLM call budget (CLAUDE.md §23.2) rather than scaling
with the number of citations found.

Each excerpt gets a three-way stance, not a boolean: "irrelevant" is a
different thing from "contradicts", and conflict detection (blueprint §8:
"when sources disagree, present both positions") depends on telling them
apart — a claim with nine irrelevant excerpts and one contradicting one is
unsupported, not conflicting; a claim with excerpts genuinely split between
supporting and contradicting is a real conflict.

The LLM's role here is narrowly a comparison/classification task — it
never introduces a fact that isn't already in the claim or the evidence
text it was given (CLAUDE.md: never state a fact with more confidence than
the sources support)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from app.evidence._llm_json import strip_code_fences
from app.evidence.connectors.base import EvidenceResult
from app.providers.base import ChatMessage, ChatRole
from app.providers.budget import LLMCallBudget
from app.providers.registry import ProviderRegistry


class Stance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    IRRELEVANT = "irrelevant"


_STANCE_VALUES: frozenset[str] = frozenset(s.value for s in Stance)

_SYSTEM_PROMPT = (
    "You are a clinical evidence-analysis assistant. You will be given a claim and a numbered "
    "list of evidence excerpts retrieved from medical sources. For EACH excerpt, classify its "
    'stance toward the claim as exactly one of: "supports", "contradicts", or "irrelevant" '
    "(the excerpt doesn't actually address the claim). Then identify any of the following "
    "issues with the claim as a whole, only when you have concrete reason from the evidence "
    "given (never guess):\n"
    '- "contradictory": excerpts disagree with each other or with the claim\n'
    '- "outdated": the supporting evidence is old and the claim may not reflect current '
    "guidance\n"
    '- "unsupported": none of the excerpts actually support the claim\n\n'
    "Respond with ONLY a JSON object of this exact shape, no other text:\n"
    '{"stances": ["supports", "contradicts", ...], "flags": [{"type": "...", "detail": "..."}]}\n'
    '"stances" must have exactly one entry per excerpt, in the same order given. Never state a '
    "fact not present in the claim or the excerpts themselves."
)

_UNSUPPORTED_FLAG = {
    "type": "unsupported",
    "detail": "No evidence was found from any configured source.",
}
_UNPARSEABLE_FLAG = {
    "type": "unsupported",
    "detail": "Evidence analysis returned an unparseable response.",
}


@dataclass(frozen=True, slots=True)
class ClaimAnalysis:
    # Parallel to the evidence list passed in.
    stances: list[Stance]
    flags: list[dict[str, str]]


async def analyze_claim(
    *,
    provider_registry: ProviderRegistry,
    claim_text: str,
    evidence: list[EvidenceResult],
    budget: LLMCallBudget | None = None,
) -> ClaimAnalysis:
    if not evidence:
        return ClaimAnalysis(stances=[], flags=[_UNSUPPORTED_FLAG])

    excerpts = "\n\n".join(
        f"[{i}] Source: {item.source.value}"
        f"{f' ({item.published_date.isoformat()})' if item.published_date else ''}\n"
        f"Title: {item.title}\n"
        f"{f'Excerpt: {item.snippet}' if item.snippet else ''}"
        for i, item in enumerate(evidence)
    )
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
        ChatMessage(
            role=ChatRole.USER, content=f"Claim: {claim_text}\n\nEvidence excerpts:\n{excerpts}"
        ),
    ]
    collected: list[str] = []
    async for _, delta in provider_registry.stream_chat(messages=messages, budget=budget):
        collected.append(delta)
    raw = "".join(collected)

    parsed = _parse_analysis(raw, expected_count=len(evidence))
    if parsed is None:
        # Malformed LLM response: an honest "we couldn't determine stance"
        # rather than guessing — every excerpt is treated as irrelevant
        # (excluded from what's shown), not silently assumed supportive.
        return ClaimAnalysis(stances=[Stance.IRRELEVANT] * len(evidence), flags=[_UNPARSEABLE_FLAG])
    return parsed


def _parse_analysis(raw: str, *, expected_count: int) -> ClaimAnalysis | None:
    try:
        data = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    stances_raw = data.get("stances")
    if (
        not isinstance(stances_raw, list)
        or len(stances_raw) != expected_count
        or not all(isinstance(item, str) and item in _STANCE_VALUES for item in stances_raw)
    ):
        return None
    stances = [Stance(item) for item in stances_raw]

    flags_raw = data.get("flags", [])
    if not isinstance(flags_raw, list):
        return None
    flags: list[dict[str, str]] = []
    for flag in flags_raw:
        if (
            isinstance(flag, dict)
            and isinstance(flag.get("type"), str)
            and isinstance(flag.get("detail"), str)
        ):
            flags.append({"type": flag["type"], "detail": flag["detail"]})

    return ClaimAnalysis(stances=stances, flags=flags)
