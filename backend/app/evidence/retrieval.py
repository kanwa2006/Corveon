"""Evidence retrieval (blueprint §8's third pipeline stage) — fans a claim
out to every registered connector concurrently and merges what comes back.

Deliberately uniform, not claim-type-aware: every claim queries all six
sources with its own raw text, rather than trying to classify "this claim
is about a drug, only query RxNorm/openFDA/DailyMed" or similar. That
classification would itself need either a hand-rolled heuristic (fragile,
silently wrong on phrasing it wasn't built for) or another LLM call
(expensive, and the extra failure mode isn't worth it for search
recall). Connectors just search well against irrelevant queries — a
ClinicalTrials.gov search for a purely definitional claim returns nothing
useful, not a wrong result, since every connector's own contract is "return
what's genuinely relevant, empty list if that's nothing" (base.py)."""

from __future__ import annotations

from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry


async def retrieve_evidence_for_claim(
    *, registry: EvidenceConnectorRegistry, claim_text: str, limit_per_source: int = 3
) -> list[EvidenceResult]:
    if not claim_text.strip():
        return []
    by_source = await registry.search_all(claim_text, limit_per_source=limit_per_source)
    merged: list[EvidenceResult] = []
    for results in by_source.values():
        merged.extend(results)
    return merged
