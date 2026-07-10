"""Evidence Verification Engine repository. Every query is scoped by
chat_id, the isolation anchor (docs/ARCHITECTURE.md §5) — same invariant
every other content repository in this codebase enforces."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.evidence import (
    EvidenceCitation,
    EvidenceClaim,
    EvidenceSourceName,
    EvidenceVerification,
    SourceClass,
    VerificationStatus,
)


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_verification(
        self, *, chat_id: uuid.UUID, message_id: uuid.UUID
    ) -> EvidenceVerification:
        verification = EvidenceVerification(chat_id=chat_id, message_id=message_id)
        self._session.add(verification)
        await self._session.flush()
        return verification

    async def update_verification_status(
        self,
        verification: EvidenceVerification,
        *,
        status: VerificationStatus,
        error: str | None = None,
    ) -> EvidenceVerification:
        verification.status = status
        if error is not None:
            verification.error = error
        await self._session.flush()
        return verification

    async def get_verification_by_id_for_chat(
        self, verification_id: uuid.UUID, chat_id: uuid.UUID
    ) -> EvidenceVerification | None:
        result = await self._session.execute(
            select(EvidenceVerification).where(
                EvidenceVerification.id == verification_id,
                EvidenceVerification.chat_id == chat_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_claim(
        self,
        *,
        chat_id: uuid.UUID,
        verification_id: uuid.UUID,
        ordinal: int,
        text: str,
        source_class: SourceClass,
        confidence_score: int,
        confidence_rationale: str,
        flags: list[dict[str, Any]] | None = None,
    ) -> EvidenceClaim:
        claim = EvidenceClaim(
            chat_id=chat_id,
            verification_id=verification_id,
            ordinal=ordinal,
            text=text,
            source_class=source_class,
            confidence_score=confidence_score,
            confidence_rationale=confidence_rationale,
            flags=flags or [],
        )
        self._session.add(claim)
        await self._session.flush()
        return claim

    async def create_citation(
        self,
        *,
        chat_id: uuid.UUID,
        claim_id: uuid.UUID,
        source: EvidenceSourceName,
        title: str,
        url: str | None = None,
        identifier: str | None = None,
        snippet: str | None = None,
        published_date: date | None = None,
        supports_claim: bool = True,
        resolved: bool = False,
    ) -> EvidenceCitation:
        citation = EvidenceCitation(
            chat_id=chat_id,
            claim_id=claim_id,
            source=source,
            title=title,
            url=url,
            identifier=identifier,
            snippet=snippet,
            published_date=published_date,
            supports_claim=supports_claim,
            resolved=resolved,
        )
        self._session.add(citation)
        await self._session.flush()
        return citation

    async def list_claims_for_verification(
        self, verification_id: uuid.UUID, chat_id: uuid.UUID
    ) -> list[EvidenceClaim]:
        result = await self._session.execute(
            select(EvidenceClaim)
            .where(
                EvidenceClaim.verification_id == verification_id, EvidenceClaim.chat_id == chat_id
            )
            .order_by(EvidenceClaim.ordinal)
        )
        return list(result.scalars().all())

    async def list_citations_for_claims(
        self, claim_ids: list[uuid.UUID], chat_id: uuid.UUID
    ) -> list[EvidenceCitation]:
        """Not a relationship traversal (no model in this codebase uses ORM
        ``relationship()`` — repositories do explicit queries, matching
        every other repository here). Callers needing claims-with-citations
        (the API response shape, blueprint §13:
        ``{claims:[{text, source_class, confidence, evidence[]}]}``) call
        this after ``list_claims_for_verification`` and group by
        ``claim_id`` themselves."""
        if not claim_ids:
            return []
        result = await self._session.execute(
            select(EvidenceCitation).where(
                EvidenceCitation.claim_id.in_(claim_ids), EvidenceCitation.chat_id == chat_id
            )
        )
        return list(result.scalars().all())
