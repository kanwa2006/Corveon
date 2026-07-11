"""Guardrailed LLM explanation narrative (blueprint §9, ADR-0020) — an
optional, additive plain-language rendering on top of a PIP or discrepancy
finding's own deterministic ``explanation``. One batched LLM call produces
a candidate narrative per finding; ``check_narrative_grounded`` then
deterministically verifies each one introduces no drug fact, number,
severity, or recommendation absent from that finding's own rule output —
anything ungrounded is discarded, never shown (CLAUDE.md: never fabricate
medical facts).

Scoped to PIP + discrepancy findings only, not Phase 1/2's interaction/
renal findings — see ADR-0020 for why those are already grounded by
construction and don't need this layer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.medication._llm_json import strip_code_fences
from app.providers.base import ChatMessage, ChatRole
from app.providers.budget import LLMCallBudget, LLMCallBudgetExceededError
from app.providers.registry import NoProviderAvailableError, ProviderRegistry

_SYSTEM_PROMPT = (
    "You write short, plain-language explanations of medication-safety findings for a "
    "clinician. You will be given a JSON array of findings, each already fully determined by "
    "a deterministic rules engine. For each finding, write ONE-to-TWO sentence explanation "
    'using ONLY the facts already given in that finding\'s object ("drug_names", "severity", '
    '"rationale", "recommendation"). Never add a drug fact, a severity, a dose, a number, or a '
    "recommendation that isn't already present in the given object. Respond with ONLY a JSON "
    "array of strings, one per input finding, in the same order as the input array — no "
    "markdown code fences, no commentary."
)

_ESCALATION_WORDS = (
    "severe",
    "critical",
    "dangerous",
    "life-threatening",
    "life threatening",
    "emergency",
    "fatal",
    "deadly",
    "urgent",
    "toxic",
)

_DIRECTIVE_PHRASES = (
    "stop taking",
    "discontinue",
    "increase the dose",
    "decrease the dose",
    "double the dose",
    "halve the dose",
    "switch to",
    "start taking",
    "reduce the dose",
    "raise the dose",
    "change the dose",
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class NarrativeFact:
    """One finding's structured rule-output, in the shape sent to the LLM
    and checked against by the grounding check. ``key`` is an opaque
    pairing token (e.g. ``"pip:0"``) the caller uses to map a returned
    narrative back to its finding — never shown to the model or the user."""

    key: str
    drug_names: list[str]
    severity: str
    rationale: str
    recommendation: str
    explanation: str


def check_narrative_grounded(
    narrative: str, *, allowed_text: str, other_drug_names: set[str]
) -> bool:
    """Returns ``False`` (ungrounded — discard) if ``narrative``:
    1. mentions a medication name known to this analysis but not this
       finding (cross-attribution — the dominant observed failure mode);
    2. contains a number not present anywhere in ``allowed_text``;
    3. contains an escalation/severity word not present in ``allowed_text``;
    4. contains a clinical-directive phrase not present in ``allowed_text``.
    A wholly invented drug name unrelated to any medication in this
    analysis is not caught by check (1) alone — documented limitation,
    ADR-0020."""
    lowered = narrative.lower()
    allowed_lowered = allowed_text.lower()

    for drug_name in other_drug_names:
        if drug_name and drug_name in lowered:
            return False

    for number in _NUMBER_RE.findall(lowered):
        if number not in allowed_lowered:
            return False

    for word in _ESCALATION_WORDS:
        if word in lowered and word not in allowed_lowered:
            return False

    for phrase in _DIRECTIVE_PHRASES:
        if phrase in lowered and phrase not in allowed_lowered:
            return False

    return True


def _allowed_text(fact: NarrativeFact) -> str:
    return " ".join(
        [fact.rationale, fact.recommendation, fact.explanation, " ".join(fact.drug_names)]
    )


async def generate_grounded_narratives(
    facts: list[NarrativeFact],
    *,
    all_drug_names: set[str],
    provider_registry: ProviderRegistry,
    budget: LLMCallBudget,
) -> dict[str, str]:
    """Returns a mapping from ``NarrativeFact.key`` to a guardrail-passed
    narrative — only for facts whose generated narrative was produced and
    passed ``check_narrative_grounded``. A missing key means "no narrative
    this time," not an error; the caller falls back to the finding's own
    deterministic ``explanation``. Degrades to an empty dict — never raises
    — on ``NoProviderAvailableError``/``LLMCallBudgetExceededError``:
    narrative generation is an enrichment on top of already-computed,
    already-persisted safety findings, not a requirement for them to exist
    (ADR-0020, consistent with ADR-0006's degraded-mode posture)."""
    if not facts:
        return {}

    payload = [
        {
            "key": fact.key,
            "drug_names": fact.drug_names,
            "severity": fact.severity,
            "rationale": fact.rationale,
            "recommendation": fact.recommendation,
        }
        for fact in facts
    ]
    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
        ChatMessage(role=ChatRole.USER, content=json.dumps(payload)),
    ]

    try:
        collected: list[str] = []
        async for _, delta in provider_registry.stream_chat(messages=messages, budget=budget):
            collected.append(delta)
    except (NoProviderAvailableError, LLMCallBudgetExceededError):
        return {}

    raw = "".join(collected)
    try:
        parsed = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, list) or len(parsed) != len(facts):
        return {}

    normalized_all_names = {name.strip().lower() for name in all_drug_names}
    results: dict[str, str] = {}
    for fact, narrative in zip(facts, parsed, strict=True):
        if not isinstance(narrative, str) or not narrative.strip():
            continue
        other_drug_names = normalized_all_names - {name.strip().lower() for name in fact.drug_names}
        if check_narrative_grounded(
            narrative, allowed_text=_allowed_text(fact), other_drug_names=other_drug_names
        ):
            results[fact.key] = narrative.strip()

    return results
