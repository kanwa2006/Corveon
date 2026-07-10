"""Source classification + confidence scoring (blueprint §8) — both fully
deterministic, no LLM call. The LLM (analysis.py) only classifies each
excerpt's stance toward the claim; everything from here on is arithmetic
over that classification, kept transparent on purpose ("never a black
box")."""

from __future__ import annotations

from datetime import date

from app.data.models.evidence import EvidenceSourceName, SourceClass
from app.evidence.analysis import Stance
from app.evidence.connectors.base import EvidenceResult

# (i) Source-class weight (blueprint §8: "verified public/org > AI
# reasoning"). Uploaded documents sit below verified-public evidence, not
# above it — CLAUDE.md's defining stance is that every uploaded document is
# potentially unreliable, so a claim resting only on the chat's own
# documents earns less confidence than one independently confirmed by a
# public source, even though it still outranks pure AI reasoning.
_BASE_SCORE_BY_SOURCE_CLASS: dict[SourceClass, int] = {
    SourceClass.VERIFIED_PUBLIC: 70,
    SourceClass.ORG_TRUSTED: 70,
    SourceClass.UPLOADED_DOCUMENT: 55,
    SourceClass.AI_REASONING: 30,
    SourceClass.CONFLICTING_INSUFFICIENT: 20,
}
_MAX_AGREEMENT_BONUS = 24
_AGREEMENT_BONUS_PER_SOURCE = 8
_RECENCY_BONUS = 6
_RECENCY_WINDOW_DAYS = 5 * 365
_MAX_RESOLUTION_BONUS = 10


def classify_source(evidence: list[EvidenceResult], stances: list[Stance]) -> SourceClass:
    """Picks the provenance class a claim's confidence score is weighted
    against. Verified-public evidence outranks the chat's own uploaded
    documents when both support the claim (see module docstring); genuine
    disagreement — whether support-vs-contradict or contradict-only —
    always lands in ``CONFLICTING_INSUFFICIENT``, never silently resolved
    toward one side (blueprint §8: present both positions, don't choose)."""
    paired = list(zip(evidence, stances, strict=True))
    supporting_sources = {item.source for item, stance in paired if stance == Stance.SUPPORTS}
    has_contradiction = any(stance == Stance.CONTRADICTS for stance in stances)

    if not supporting_sources and not has_contradiction:
        return SourceClass.AI_REASONING
    if has_contradiction:
        return SourceClass.CONFLICTING_INSUFFICIENT

    external_sources = supporting_sources - {EvidenceSourceName.UPLOADED_DOCUMENT}
    return SourceClass.VERIFIED_PUBLIC if external_sources else SourceClass.UPLOADED_DOCUMENT


def score_confidence(
    *,
    source_class: SourceClass,
    evidence: list[EvidenceResult],
    stances: list[Stance],
    resolved: list[bool],
    today: date,
) -> tuple[int, str]:
    """Returns (0-100 score, plain-language rationale) — the score is
    always fully reconstructable from the rationale string, per blueprint
    §8's "documented, never a black box"."""
    base = _BASE_SCORE_BY_SOURCE_CLASS[source_class]

    supporting = [
        item for item, stance in zip(evidence, stances, strict=True) if stance == Stance.SUPPORTS
    ]
    distinct_sources = {item.source for item in supporting}
    agreement_bonus = min(len(distinct_sources) * _AGREEMENT_BONUS_PER_SOURCE, _MAX_AGREEMENT_BONUS)

    dated_supporting = [item for item in supporting if item.published_date is not None]
    recent_supporting = [
        item
        for item in dated_supporting
        if item.published_date is not None
        and (today - item.published_date).days < _RECENCY_WINDOW_DAYS
    ]
    recency_bonus = (
        _RECENCY_BONUS
        if dated_supporting and len(recent_supporting) / len(dated_supporting) >= 0.5
        else 0
    )

    resolution_rate = (sum(resolved) / len(resolved)) if resolved else 0.0
    resolution_bonus = round(resolution_rate * _MAX_RESOLUTION_BONUS)

    score = max(0, min(100, base + agreement_bonus + recency_bonus + resolution_bonus))
    rationale = (
        f"Base {base} for {source_class.value} evidence; "
        f"+{agreement_bonus} for {len(distinct_sources)} independent supporting source(s); "
        f"+{recency_bonus} for recency; "
        f"+{resolution_bonus} for a {resolution_rate:.0%} citation-resolution rate."
    )
    return score, rationale
