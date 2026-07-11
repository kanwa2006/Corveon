"""Medication-Safety Engine data model (blueprint §9, §10.1) — normalization
+ drug-drug interaction detection (Phase 1), renal/dose checks (Phase 2,
ADR-0005). Every table carries ``chat_id``, the isolation anchor (§5),
matching every other content-bearing table in this codebase.

``medication_findings`` augments the blueprint's minimal ``(chat_id, type,
severity, source, rule_id, explanation, provenance)`` shape with two
nullable medication foreign keys — the blueprint's own schema otherwise
leaves a finding with no way to say which medications it concerns, which
would make an ``interaction`` finding unusable. ``medication_a_id`` is
always populated; ``medication_b_id`` is populated for pairwise finding
types (interaction) and left null for single-medication types a later
phase adds (renal, PIP)."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class FindingType(StrEnum):
    """Finding categories (blueprint §9) — only INTERACTION is produced in
    this phase; RENAL/PIP/DISCREPANCY are real, reserved values later
    phases (dual renal equations, Beers/STOPP-START, discrepancy diff)
    will produce, not placeholders."""

    INTERACTION = "interaction"
    RENAL = "renal"
    PIP = "pip"
    DISCREPANCY = "discrepancy"


class FindingSeverity(StrEnum):
    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"
    # openFDA's label-derived fallback surfaces raw label text, not a
    # DDInter-computed severity — an honest "we found something, a
    # clinician should read it" rather than inventing a severity tier the
    # source didn't provide.
    UNCLASSIFIED = "unclassified"


class InteractionSource(StrEnum):
    """Where a finding's verdict came from. Despite the name (kept from
    Phase 1, where every finding was a drug-drug interaction), this enum is
    reused for every finding type sharing ``medication_findings.source`` —
    CALCULATED covers deterministic, formula-derived findings (Phase 2's
    renal checks; a later phase's Beers/STOPP-START rule matches), as
    opposed to DDINTER/OPENFDA_LABEL's external-source lookups."""

    DDINTER = "ddinter"
    OPENFDA_LABEL = "openfda_label"
    CALCULATED = "calculated"


def _enum_column(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Medication(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One normalized medication entry from an analyze request. ``rxcui`` is
    null when RxNorm had no match for the parsed name — the medication is
    still recorded (an unmatched drug is itself useful information) but
    can't participate in RxCUI-keyed interaction checks."""

    __tablename__ = "medications"
    __table_args__ = (Index("ix_medications_chat_id", "chat_id"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    rxcui: Mapped[str | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(nullable=False)
    dose: Mapped[str | None] = mapped_column(nullable=True)
    route: Mapped[str | None] = mapped_column(nullable=True)
    frequency: Mapped[str | None] = mapped_column(nullable=True)


class MedicationFinding(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One rules-engine finding (blueprint §9) — deterministic output only;
    the LLM never contributes to ``severity``/``rule_id``/``provenance``,
    only to a later human-readable explanation layered on top (guardrailed,
    a later phase)."""

    __tablename__ = "medication_findings"
    __table_args__ = (Index("ix_medication_findings_chat_id", "chat_id"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    medication_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    medication_b_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[FindingType] = mapped_column(
        _enum_column(FindingType, "medication_finding_type"), nullable=False
    )
    severity: Mapped[FindingSeverity] = mapped_column(
        _enum_column(FindingSeverity, "medication_finding_severity"), nullable=False
    )
    source: Mapped[InteractionSource] = mapped_column(
        _enum_column(InteractionSource, "medication_interaction_source"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DrugDataSnapshot(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One imported, checksum-verified reference-data snapshot (blueprint
    §10.4) — reproducibility/auditability record, not chat-scoped (this is
    shared reference data, not per-chat content)."""

    __tablename__ = "drug_data_snapshots"

    source: Mapped[str] = mapped_column(nullable=False)
    version: Mapped[str] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(nullable=False)
    row_count: Mapped[int] = mapped_column(nullable=False)


class DrugInteraction(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One DDInter 2.0 interaction record from an imported snapshot —
    shared reference data (not chat-scoped, no RLS, like
    ``DrugDataSnapshot``). DDInter is keyed by drug name, not RxCUI, so
    lookup matches on normalized (lowercased, trimmed) generic name rather
    than RxCUI; ``drug_a_name``/``drug_b_name`` are always stored in sorted
    order so a pairwise lookup only needs to check one direction."""

    __tablename__ = "drug_interactions"
    __table_args__ = (
        Index("ix_drug_interactions_pair", "drug_a_name", "drug_b_name"),
        Index("ix_drug_interactions_snapshot_id", "snapshot_id"),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drug_data_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    drug_a_name: Mapped[str] = mapped_column(nullable=False)
    drug_b_name: Mapped[str] = mapped_column(nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(
        _enum_column(FindingSeverity, "medication_finding_severity"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
