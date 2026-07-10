"""Free-text medication parsing + RxNorm normalization (blueprint §9:
"Ingestion... A normalizer maps every drug to RxCUI via RxNorm/RxNav").

The LLM's role here is narrowly extraction — turning messy free text into
structured (name, dose, route, frequency) fields already present in the
input text. It never infers a drug's RxCUI, interactions, or any other
fact; RxNorm normalization is a separate, deterministic lookup on the
extracted name (CLAUDE.md §6: the LLM only parses input into structured
entries; the rules engine and its data sources are the source of truth)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.medication._llm_json import strip_code_fences
from app.medication.rxnorm_client import SupportsNormalize
from app.providers.base import ChatMessage, ChatRole
from app.providers.budget import LLMCallBudget
from app.providers.registry import ProviderRegistry

_SYSTEM_PROMPT = (
    "You are a medication-list parsing assistant. Given free text describing one or more "
    "medications (e.g. a discharge summary line, a patient-reported list), extract each "
    'distinct medication as a JSON object with these fields: "raw_text" (the exact source '
    'fragment for this medication), "name" (the drug name as written), "dose" (e.g. "500mg", '
    'or null if not stated), "route" (e.g. "oral", "IV", or null if not stated), '
    '"frequency" (e.g. "twice daily", or null if not stated). Extract only what the text '
    "actually states — never infer a dose, route, or frequency the text doesn't contain, and "
    "never add a medication not mentioned. Respond with ONLY a JSON array of these objects — no "
    "markdown code fences, no commentary."
)

_MAX_ENTRIES = 25


@dataclass(frozen=True, slots=True)
class ParsedMedicationEntry:
    raw_text: str
    name: str
    dose: str | None
    route: str | None
    frequency: str | None


async def parse_medication_entries(
    *, provider_registry: ProviderRegistry, text: str, budget: LLMCallBudget | None = None
) -> list[ParsedMedicationEntry]:
    """Returns up to ``_MAX_ENTRIES`` parsed entries. Never raises on a
    malformed LLM response — falls back to treating the whole input as one
    unparsed entry (name = raw text), an honest degraded result (the entry
    can still be looked up / flagged as unmatched) rather than losing the
    request to a JSON-parsing edge case (matches
    app/evidence/claim_extraction.py's same fallback posture)."""
    stripped = text.strip()
    if not stripped:
        return []

    messages = [
        ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
        ChatMessage(role=ChatRole.USER, content=stripped),
    ]
    collected: list[str] = []
    async for _, delta in provider_registry.stream_chat(messages=messages, budget=budget):
        collected.append(delta)
    raw = "".join(collected)

    entries = _parse_entries(raw)
    if entries is None:
        return [
            ParsedMedicationEntry(
                raw_text=stripped, name=stripped, dose=None, route=None, frequency=None
            )
        ]
    return entries[:_MAX_ENTRIES]


def _clean_optional_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _parse_entries(raw: str) -> list[ParsedMedicationEntry] | None:
    try:
        parsed = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None

    entries: list[ParsedMedicationEntry] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        raw_text = item.get("raw_text")
        if not isinstance(name, str) or not name.strip():
            return None
        entries.append(
            ParsedMedicationEntry(
                raw_text=raw_text if isinstance(raw_text, str) and raw_text.strip() else name,
                name=name.strip(),
                dose=_clean_optional_str(item.get("dose")),
                route=_clean_optional_str(item.get("route")),
                frequency=_clean_optional_str(item.get("frequency")),
            )
        )
    return entries


async def normalize_entry(
    entry: ParsedMedicationEntry, *, rxnorm_client: SupportsNormalize
) -> tuple[str | None, str]:
    """Returns ``(rxcui, name)`` — ``rxcui`` is None when RxNav had no
    match; ``name`` is RxNav's canonical name when matched, otherwise the
    entry's own parsed name (an unmatched drug is still recorded, not
    dropped — blueprint §9's "insufficient data" posture, not a hard
    failure)."""
    match = await rxnorm_client.normalize(entry.name)
    if match is None:
        return None, entry.name
    return match.rxcui, match.canonical_name
