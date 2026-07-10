"""Claim/segment extraction (blueprint §8's first pipeline stage). Splitting
a passage into independent, verifiable claims isn't a deterministic-rules
problem the way medication-dose math is (CLAUDE.md §9 reserves "rules
engine is truth" for that domain specifically) — it needs real language
understanding, so this step goes through the provider registry like any
other LLM call, with the output schema-validated before anything downstream
trusts it (CLAUDE.md §5: "agent outputs are schema-validated")."""

from __future__ import annotations

import json

from app.evidence._llm_json import strip_code_fences
from app.providers.base import ChatMessage, ChatRole
from app.providers.budget import LLMCallBudget
from app.providers.registry import ProviderRegistry

_SYSTEM_PROMPT = (
    "You are a claim-extraction assistant for a clinical evidence-verification system. "
    "Given a passage of text, break it into a JSON array of independent, verifiable factual "
    "claims. Each claim must be a complete, self-contained statement that could be checked "
    "against a medical source — not a sentence fragment, not a question, not an opinion, not a "
    "greeting or pleasantry. If the text contains no verifiable factual claims (e.g. it is "
    "purely conversational or a question), return an empty array. Respond with ONLY a JSON "
    "array of strings — no markdown code fences, no commentary, no other text."
)


async def extract_claims(
    *,
    provider_registry: ProviderRegistry,
    text: str,
    max_claims: int = 10,
    budget: LLMCallBudget | None = None,
) -> list[str]:
    """Returns up to ``max_claims`` extracted claim strings. Never raises on
    a malformed LLM response — falls back to treating the whole input as a
    single claim, an honest degraded result (some verification is still
    possible) rather than losing the request to a JSON-parsing edge case."""
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

    claims = _parse_claims(raw)
    if claims is None:
        return [stripped]
    return claims[:max_claims]


def _parse_claims(raw: str) -> list[str] | None:
    try:
        parsed = json.loads(strip_code_fences(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        return None
    return [item.strip() for item in parsed if item.strip()]
