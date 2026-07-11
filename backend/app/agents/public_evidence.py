"""Public Evidence Retrieval agent (blueprint §7, ADR-0021) — the
RAG-public-evidence routing branch: when a chat has no uploaded documents to
ground on, search the same six public medical-evidence connectors the
Evidence Verification Engine already uses (PubMed, DailyMed, openFDA,
ClinicalTrials.gov, MeSH, RxNorm) instead of falling through to an
ungrounded pure-LLM answer. Reuses ``retrieve_evidence_for_claim`` verbatim
— it is already a generic "evidence for this text" call, not
claim-specific — so this agent adds no new retrieval logic of its own."""

from __future__ import annotations

from app.agents.state import OrchestratorState
from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry
from app.evidence.retrieval import retrieve_evidence_for_claim


async def retrieve_public_evidence(
    *, registry: EvidenceConnectorRegistry, query: str
) -> list[EvidenceResult]:
    return await retrieve_evidence_for_claim(registry=registry, claim_text=query)


class PublicEvidenceAgent:
    name = "public_evidence"

    def __init__(self, registry: EvidenceConnectorRegistry) -> None:
        self._registry = registry

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        state.public_evidence = await retrieve_public_evidence(
            registry=self._registry, query=state.user_query
        )
        return state
