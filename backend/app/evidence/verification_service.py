"""Evidence Verification service — the blueprint §8 pipeline assembled end
to end: claim extraction -> per-claim retrieval (this chat's own uploaded
documents *and* the six public connectors) -> stance analysis -> source
classification -> confidence scoring -> citation verification ->
persistence. An async generator yielding one item per completed claim (plus
a final ``done``), so the API layer can stream results as they're ready
rather than waiting for every claim in a multi-claim message to finish.

Not built as an ``app.agents.base.Agent`` — that protocol's shared state
(``OrchestratorState``) is shaped around the message-send routing pipeline
(chat_id + a single user query, mutated in place by three sequential
steps); this pipeline runs per-claim in a loop with incremental persistence
and its own DB-session lifecycle, a different enough shape that forcing it
into ``OrchestratorState`` would distort that type rather than reuse it
cleanly. It fully preserves that module's actual point — Week 1/Month 1
code is untouched, and a future subsystem (org-trusted sources) still only
adds a new connector, not a rewrite here."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.agents.retrieval import MIN_SIMILARITY, TOP_K
from app.data.models.evidence import EvidenceSourceName, VerificationStatus
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.repositories.evidence_repository import EvidenceRepository
from app.evidence.analysis import Stance, analyze_claim
from app.evidence.citation_verification import is_citation_resolved
from app.evidence.claim_extraction import extract_claims
from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry
from app.evidence.scoring import classify_source, score_confidence
from app.ingestion.embeddings import EmbeddingModel
from app.providers.budget import LLMCallBudget, LLMCallBudgetExceededError
from app.providers.registry import NoProviderAvailableError, ProviderRegistry


@dataclass(frozen=True, slots=True)
class VerifiedCitation:
    source: EvidenceSourceName
    title: str
    url: str | None
    identifier: str | None
    published_date: date | None
    supports_claim: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "title": self.title,
            "url": self.url,
            "identifier": self.identifier,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "supports_claim": self.supports_claim,
        }


@dataclass(frozen=True, slots=True)
class VerifiedClaim:
    id: uuid.UUID
    ordinal: int
    text: str
    source_class: str
    confidence_score: int
    confidence_rationale: str
    flags: list[dict[str, str]]
    citations: list[VerifiedCitation]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "ordinal": self.ordinal,
            "text": self.text,
            "source_class": self.source_class,
            "confidence_score": self.confidence_score,
            "confidence_rationale": self.confidence_rationale,
            "flags": self.flags,
            "citations": [c.as_dict() for c in self.citations],
        }


async def _retrieve_uploaded_document_evidence(
    *,
    chunk_repo: ChunkRepository,
    embedding_model: EmbeddingModel,
    chat_id: uuid.UUID,
    claim_text: str,
) -> list[EvidenceResult]:
    """Same retrieval primitives and threshold as app/agents/retrieval.py's
    chat-message grounding (TOP_K, MIN_SIMILARITY) — a claim's own uploaded-
    document evidence is held to the same relevance bar as a normal
    RAG-grounded chat answer."""
    has_chunks = await chunk_repo.has_ready_chunks(
        chat_id=chat_id, model_id=embedding_model.model_id
    )
    if not has_chunks:
        return []
    query_vector = embedding_model.embed_query(claim_text)
    hits = await chunk_repo.similarity_search(
        chat_id=chat_id, model_id=embedding_model.model_id, query_vector=query_vector, top_k=TOP_K
    )
    return [
        EvidenceResult(
            source=EvidenceSourceName.UPLOADED_DOCUMENT,
            title=document.filename,
            url=None,
            identifier=str(chunk.id),
            snippet=chunk.text[:500],
            published_date=None,
        )
        for chunk, document, distance in hits
        if (1 - distance) >= MIN_SIMILARITY
    ]


async def run_verification(
    *,
    chat_id: uuid.UUID,
    verification_id: uuid.UUID,
    message_text: str,
    provider_registry: ProviderRegistry,
    connector_registry: EvidenceConnectorRegistry,
    chunk_repo: ChunkRepository,
    embedding_model: EmbeddingModel,
    evidence_repo: EvidenceRepository,
    max_llm_calls: int,
) -> AsyncIterator[VerifiedClaim]:
    """Yields one ``VerifiedClaim`` per completed claim, already persisted
    (claim + its shown citations flushed, not committed — the caller owns
    the transaction/RLS-reapply boundary, same division of responsibility
    as app/orchestrator/chat_orchestrator.py's stream_response).

    Raises ``NoProviderAvailableError``/``LLMCallBudgetExceededError`` on a
    degraded-mode condition, after marking the verification row FAILED —
    any claims already yielded before the failure remain persisted (a
    partial result is still real, useful evidence, not discarded)."""
    verification = await evidence_repo.get_verification_by_id_for_chat(verification_id, chat_id)
    if verification is None:
        raise ValueError(f"Verification {verification_id} not found for chat {chat_id}.")

    budget = LLMCallBudget(max_llm_calls)

    try:
        claim_texts = await extract_claims(
            provider_registry=provider_registry, text=message_text, budget=budget
        )
    except (NoProviderAvailableError, LLMCallBudgetExceededError) as exc:
        await evidence_repo.update_verification_status(
            verification, status=VerificationStatus.FAILED, error=str(exc)
        )
        raise

    for ordinal, claim_text in enumerate(claim_texts):
        try:
            uploaded_evidence = await _retrieve_uploaded_document_evidence(
                chunk_repo=chunk_repo,
                embedding_model=embedding_model,
                chat_id=chat_id,
                claim_text=claim_text,
            )
            external_by_source = await connector_registry.search_all(claim_text)
            external_evidence = [
                result for results in external_by_source.values() for result in results
            ]
            evidence = uploaded_evidence + external_evidence

            analysis = await analyze_claim(
                provider_registry=provider_registry,
                claim_text=claim_text,
                evidence=evidence,
                budget=budget,
            )
        except (NoProviderAvailableError, LLMCallBudgetExceededError) as exc:
            await evidence_repo.update_verification_status(
                verification, status=VerificationStatus.FAILED, error=str(exc)
            )
            raise

        source_class = classify_source(evidence, analysis.stances)
        resolved = [is_citation_resolved(item) for item in evidence]
        score, rationale = score_confidence(
            source_class=source_class,
            evidence=evidence,
            stances=analysis.stances,
            resolved=resolved,
            today=date.today(),
        )

        claim_row = await evidence_repo.create_claim(
            chat_id=chat_id,
            verification_id=verification.id,
            ordinal=ordinal,
            text=claim_text,
            source_class=source_class,
            confidence_score=score,
            confidence_rationale=rationale,
            flags=analysis.flags,
        )

        citations: list[VerifiedCitation] = []
        for item, stance, item_resolved in zip(evidence, analysis.stances, resolved, strict=True):
            # Irrelevant excerpts were never real support/contradiction for
            # this claim — not shown. Unresolved citations are the
            # fabricated-citation guard's negative case (CLAUDE.md: "it is
            # flagged, not shown") — also not shown, only reflected in the
            # confidence score's resolution-rate penalty.
            if stance == Stance.IRRELEVANT or not item_resolved:
                continue
            await evidence_repo.create_citation(
                chat_id=chat_id,
                claim_id=claim_row.id,
                source=item.source,
                title=item.title,
                url=item.url,
                identifier=item.identifier,
                snippet=item.snippet,
                published_date=item.published_date,
                supports_claim=(stance == Stance.SUPPORTS),
                resolved=item_resolved,
            )
            citations.append(
                VerifiedCitation(
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    identifier=item.identifier,
                    published_date=item.published_date,
                    supports_claim=(stance == Stance.SUPPORTS),
                )
            )

        yield VerifiedClaim(
            id=claim_row.id,
            ordinal=ordinal,
            text=claim_text,
            source_class=source_class.value,
            confidence_score=score,
            confidence_rationale=rationale,
            flags=analysis.flags,
            citations=citations,
        )

    await evidence_repo.update_verification_status(
        verification, status=VerificationStatus.SUCCEEDED
    )
