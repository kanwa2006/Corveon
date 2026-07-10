"""Unit tests for source classification and confidence scoring
(app/evidence/scoring.py) — fully deterministic, no LLM/network involved."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.data.models.evidence import EvidenceSourceName, SourceClass
from app.evidence.analysis import Stance
from app.evidence.connectors.base import EvidenceResult
from app.evidence.scoring import classify_source, score_confidence

pytestmark = pytest.mark.unit

_TODAY = date(2026, 1, 1)


def _evidence(source: EvidenceSourceName, *, published_date: date | None = None) -> EvidenceResult:
    return EvidenceResult(
        source=source,
        title="Title",
        url="https://example.org",
        identifier="id",
        snippet=None,
        published_date=published_date,
    )


# ── classify_source ──────────────────────────────────────────────────────


def test_classify_source_returns_ai_reasoning_when_nothing_relevant() -> None:
    evidence = [_evidence(EvidenceSourceName.PUBMED)]
    stances = [Stance.IRRELEVANT]
    assert classify_source(evidence, stances) == SourceClass.AI_REASONING


def test_classify_source_returns_ai_reasoning_for_no_evidence_at_all() -> None:
    assert classify_source([], []) == SourceClass.AI_REASONING


def test_classify_source_returns_verified_public_when_external_source_supports() -> None:
    evidence = [_evidence(EvidenceSourceName.PUBMED)]
    stances = [Stance.SUPPORTS]
    assert classify_source(evidence, stances) == SourceClass.VERIFIED_PUBLIC


def test_classify_source_returns_uploaded_document_when_only_the_chat_doc_supports() -> None:
    evidence = [_evidence(EvidenceSourceName.UPLOADED_DOCUMENT)]
    stances = [Stance.SUPPORTS]
    assert classify_source(evidence, stances) == SourceClass.UPLOADED_DOCUMENT


def test_classify_source_prefers_verified_public_when_both_support() -> None:
    evidence = [
        _evidence(EvidenceSourceName.UPLOADED_DOCUMENT),
        _evidence(EvidenceSourceName.PUBMED),
    ]
    stances = [Stance.SUPPORTS, Stance.SUPPORTS]
    assert classify_source(evidence, stances) == SourceClass.VERIFIED_PUBLIC


def test_classify_source_is_conflicting_when_support_and_contradiction_both_present() -> None:
    evidence = [_evidence(EvidenceSourceName.PUBMED), _evidence(EvidenceSourceName.DAILYMED)]
    stances = [Stance.SUPPORTS, Stance.CONTRADICTS]
    assert classify_source(evidence, stances) == SourceClass.CONFLICTING_INSUFFICIENT


def test_classify_source_is_conflicting_for_contradiction_only_no_support() -> None:
    evidence = [_evidence(EvidenceSourceName.PUBMED)]
    stances = [Stance.CONTRADICTS]
    assert classify_source(evidence, stances) == SourceClass.CONFLICTING_INSUFFICIENT


# ── score_confidence ─────────────────────────────────────────────────────


def test_score_confidence_ai_reasoning_has_no_evidence_bonuses() -> None:
    score, rationale = score_confidence(
        source_class=SourceClass.AI_REASONING,
        evidence=[],
        stances=[],
        resolved=[],
        today=_TODAY,
    )
    assert score == 30
    assert "Base 30 for ai_reasoning" in rationale


def test_score_confidence_rewards_independent_supporting_sources() -> None:
    evidence = [
        _evidence(EvidenceSourceName.PUBMED, published_date=_TODAY),
        _evidence(EvidenceSourceName.DAILYMED, published_date=_TODAY),
        _evidence(EvidenceSourceName.OPENFDA, published_date=_TODAY),
    ]
    stances = [Stance.SUPPORTS, Stance.SUPPORTS, Stance.SUPPORTS]
    score, rationale = score_confidence(
        source_class=SourceClass.VERIFIED_PUBLIC,
        evidence=evidence,
        stances=stances,
        resolved=[True, True, True],
        today=_TODAY,
    )
    # base 70 + agreement (3 sources * 8 = 24, capped at 24) + recency (6) + resolution (10)
    assert score == 100
    assert "3 independent supporting source(s)" in rationale


def test_score_confidence_gives_no_recency_bonus_for_old_evidence() -> None:
    old_date = _TODAY - timedelta(days=10 * 365)
    evidence = [_evidence(EvidenceSourceName.PUBMED, published_date=old_date)]
    score_old, _ = score_confidence(
        source_class=SourceClass.VERIFIED_PUBLIC,
        evidence=evidence,
        stances=[Stance.SUPPORTS],
        resolved=[True],
        today=_TODAY,
    )

    recent_evidence = [_evidence(EvidenceSourceName.PUBMED, published_date=_TODAY)]
    score_recent, _ = score_confidence(
        source_class=SourceClass.VERIFIED_PUBLIC,
        evidence=recent_evidence,
        stances=[Stance.SUPPORTS],
        resolved=[True],
        today=_TODAY,
    )

    assert score_recent > score_old


def test_score_confidence_rewards_citation_resolution_rate() -> None:
    evidence = [_evidence(EvidenceSourceName.PUBMED), _evidence(EvidenceSourceName.DAILYMED)]
    stances = [Stance.SUPPORTS, Stance.SUPPORTS]

    fully_resolved_score, _ = score_confidence(
        source_class=SourceClass.VERIFIED_PUBLIC,
        evidence=evidence,
        stances=stances,
        resolved=[True, True],
        today=_TODAY,
    )
    unresolved_score, _ = score_confidence(
        source_class=SourceClass.VERIFIED_PUBLIC,
        evidence=evidence,
        stances=stances,
        resolved=[False, False],
        today=_TODAY,
    )

    assert fully_resolved_score > unresolved_score


def test_score_confidence_is_always_between_0_and_100() -> None:
    score, _ = score_confidence(
        source_class=SourceClass.CONFLICTING_INSUFFICIENT,
        evidence=[],
        stances=[],
        resolved=[],
        today=_TODAY,
    )
    assert 0 <= score <= 100
