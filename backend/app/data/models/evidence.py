"""Evidence Verification Engine data model (blueprint §8, §10.1). Every table
carries ``chat_id`` — the isolation anchor (§5) — even though each row also
reaches it transitively via ``verification_id``/``claim_id``, matching the
denormalization pattern ``document_chunks``/``chunk_embeddings`` already
established: every content query filters directly on ``chat_id`` without a
join, and RLS applies uniformly across every content-bearing table."""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VerificationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SourceClass(StrEnum):
    """Provenance classes (blueprint §8) — every claim gets exactly one."""

    UPLOADED_DOCUMENT = "uploaded_document"
    VERIFIED_PUBLIC = "verified_public"
    # A real classification, not a placeholder: org-trusted corpora are a
    # distinct, versioned, access-scoped source (blueprint §8) that this
    # phase does not build a registration/ingestion path for. No claim is
    # ever tagged this class until that subsystem exists — an honest "this
    # source class is real but currently unreachable," not a fake feature.
    ORG_TRUSTED = "org_trusted"
    AI_REASONING = "ai_reasoning"
    CONFLICTING_INSUFFICIENT = "conflicting_insufficient"


class EvidenceSourceName(StrEnum):
    """External connectors + the two non-external provenance origins a
    citation can point back to."""

    PUBMED = "pubmed"
    DAILYMED = "dailymed"
    OPENFDA = "openfda"
    CLINICALTRIALS = "clinicaltrials"
    MESH = "mesh"
    RXNORM = "rxnorm"
    UPLOADED_DOCUMENT = "uploaded_document"


def _enum_column(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class EvidenceVerification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One verification run against a single message's claims."""

    __tablename__ = "evidence_verifications"
    __table_args__ = (Index("ix_evidence_verifications_chat_id", "chat_id"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[VerificationStatus] = mapped_column(
        _enum_column(VerificationStatus, "verification_status"),
        nullable=False,
        server_default=VerificationStatus.PENDING.value,
    )
    error: Mapped[str | None] = mapped_column(nullable=True)


class EvidenceClaim(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One extracted, independently-verifiable claim from the verified
    message, tagged with its provenance, confidence, and any detection
    flags (blueprint §8: contradiction/outdatedness/fabrication)."""

    __tablename__ = "evidence_claims"
    __table_args__ = (Index("ix_evidence_claims_chat_id", "chat_id"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_verifications.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_class: Mapped[SourceClass] = mapped_column(
        _enum_column(SourceClass, "evidence_source_class"), nullable=False
    )
    confidence_score: Mapped[int] = mapped_column(nullable=False)
    confidence_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured detection flags — [{"type": "outdated"|"unsupported"|
    # "contradictory"|"fabricated_citation", "detail": "..."}], never prose
    # baked into `text` (CLAUDE.md: agent outputs are schema-validated).
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class EvidenceCitation(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One evidence record backing (or contradicting) a claim. ``resolved``
    is the fabricated-citation guard's verdict — false means this citation
    did not resolve to a real record at the source and must not be
    presented to the user as support (blueprint §8)."""

    __tablename__ = "evidence_citations"
    __table_args__ = (Index("ix_evidence_citations_chat_id", "chat_id"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_claims.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[EvidenceSourceName] = mapped_column(
        _enum_column(EvidenceSourceName, "evidence_source_name"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(nullable=True)
    identifier: Mapped[str | None] = mapped_column(nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_date: Mapped[date | None] = mapped_column(nullable=True)
    supports_claim: Mapped[bool] = mapped_column(nullable=False, default=True)
    resolved: Mapped[bool] = mapped_column(nullable=False, default=False)
