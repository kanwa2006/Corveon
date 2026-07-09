"""Query Understanding agent (blueprint §7) — deterministic trivial-input
detection for the low-latency fast-path (§23.5). Not an LLM call: paying a
full provider round-trip just to classify would defeat the point of a *fast*
path, and a deterministic allow-list is exactly as auditable as the rest of
this policy."""

from __future__ import annotations

import re

from app.agents.state import OrchestratorState

# A deliberately small, explicit allow-list — greetings, acknowledgements,
# and other conversational turns that never benefit from retrieval. Revisit
# with a learned classifier only if this demonstrably under-covers real
# traffic; until then a fixed list is cheaper and exactly as auditable as
# every other deterministic step in this policy.
_TRIVIAL_PHRASES = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "hiya",
        "yo",
        "howdy",
        "thanks",
        "thank you",
        "thx",
        "ty",
        "bye",
        "goodbye",
        "see you",
        "later",
        "ok",
        "okay",
        "sure",
        "yes",
        "no",
        "yep",
        "nope",
        "yeah",
        "nah",
        "cool",
        "great",
        "nice",
        "got it",
        "sounds good",
    }
)


def classify_intent(user_query: str) -> bool:
    """True when ``user_query`` is a trivial, self-contained conversational
    turn that should take the fast-path (§23.5) regardless of whether this
    chat has documents. A plain function (not just the agent's ``run``) since
    Task Planning needs the classification result before it knows whether
    the rest of the pipeline runs at all."""
    normalized = re.sub(r"[!.?]+$", "", user_query.strip().lower())
    return normalized in _TRIVIAL_PHRASES or len(normalized) <= 2


class QueryUnderstandingAgent:
    name = "query_understanding"

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        state.is_trivial = classify_intent(state.user_query)
        return state
