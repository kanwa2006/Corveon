"""Medication-Safety Engine analysis service (blueprint §9) — given free
text describing a patient's medications, parses it into structured
entries, normalizes each to RxCUI via RxNorm, persists them, then runs the
deterministic DDI rules engine (Phase 1) and, when renal parameters are
supplied, the deterministic renal-dosing threshold checks (Phase 2,
ADR-0005) — persisting findings as they're produced. An async generator
yielding one item per completed medication, then one item per interaction
finding, then one item per renal finding, so the API layer can stream
results as they're ready rather than waiting for the whole analysis to
finish — same incremental-streaming shape as
app/evidence/verification_service.py.

Not built as an app.agents.base.Agent, for the same reason
verification_service.py isn't: this pipeline's shape (parse once, then loop
persisting entries, then loop persisting pairwise findings) doesn't fit
OrchestratorState's single-query shape any better than evidence
verification's per-claim loop did. See that module's own docstring."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.medication import FindingType, InteractionSource
from app.data.repositories.medication_repository import MedicationRepository
from app.medication.interactions import (
    NormalizedMedication,
    SupportsCheckPair,
    find_interactions,
)
from app.medication.normalizer import normalize_entry, parse_medication_entries
from app.medication.renal import RenalParameters, check_renal_thresholds
from app.medication.rxnorm_client import SupportsNormalize
from app.providers.budget import LLMCallBudget
from app.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class NormalizedMedicationResult:
    id: uuid.UUID
    raw_text: str
    name: str
    rxcui: str | None
    dose: str | None
    route: str | None
    frequency: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "raw_text": self.raw_text,
            "name": self.name,
            "rxcui": self.rxcui,
            "dose": self.dose,
            "route": self.route,
            "frequency": self.frequency,
        }


@dataclass(frozen=True, slots=True)
class InteractionFindingResult:
    id: uuid.UUID
    medication_a_id: uuid.UUID
    medication_b_id: uuid.UUID
    severity: str
    source: str
    rule_id: str
    explanation: str
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "medication_a_id": str(self.medication_a_id),
            "medication_b_id": str(self.medication_b_id),
            "severity": self.severity,
            "source": self.source,
            "rule_id": self.rule_id,
            "explanation": self.explanation,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class RenalFindingResult:
    id: uuid.UUID
    medication_id: uuid.UUID
    crcl_ml_min: float
    egfr_ml_min: float
    threshold_ml_min: float
    severity: str
    rule_id: str
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "medication_id": str(self.medication_id),
            "crcl_ml_min": self.crcl_ml_min,
            "egfr_ml_min": self.egfr_ml_min,
            "threshold_ml_min": self.threshold_ml_min,
            "severity": self.severity,
            "rule_id": self.rule_id,
            "explanation": self.explanation,
        }


async def run_medication_analysis(
    *,
    chat_id: uuid.UUID,
    raw_text: str,
    renal_params: RenalParameters | None,
    provider_registry: ProviderRegistry,
    rxnorm_client: SupportsNormalize,
    openfda_ddi_client: SupportsCheckPair,
    session: AsyncSession,
    medication_repo: MedicationRepository,
    max_llm_calls: int,
) -> AsyncIterator[NormalizedMedicationResult | InteractionFindingResult | RenalFindingResult]:
    """Yields a ``NormalizedMedicationResult`` per parsed-and-persisted
    medication, then an ``InteractionFindingResult`` per DDI finding, then
    — only when ``renal_params`` is given — a ``RenalFindingResult`` per
    threshold-sensitive medication whose renal function warrants a flag.
    Exactly one LLM call total (free-text parsing) — normalization,
    interaction detection, and renal checks are all fully deterministic, so
    this stays well within the per-request budget regardless of
    medication-list length.

    Raises ``NoProviderAvailableError``/``LLMCallBudgetExceededError`` on a
    degraded-mode condition — propagated to the caller unchanged, same
    division of responsibility as verification_service.run_verification."""
    budget = LLMCallBudget(max_llm_calls)
    entries = await parse_medication_entries(
        provider_registry=provider_registry, text=raw_text, budget=budget
    )

    normalized: list[NormalizedMedication] = []
    persisted_ids: list[uuid.UUID] = []
    for entry in entries:
        rxcui, name = await normalize_entry(entry, rxnorm_client=rxnorm_client)
        medication_row = await medication_repo.create_medication(
            chat_id=chat_id,
            raw_text=entry.raw_text,
            name=name,
            rxcui=rxcui,
            dose=entry.dose,
            route=entry.route,
            frequency=entry.frequency,
        )
        normalized.append(
            NormalizedMedication(
                raw_text=entry.raw_text,
                name=name,
                rxcui=rxcui,
                dose=entry.dose,
                route=entry.route,
                frequency=entry.frequency,
            )
        )
        persisted_ids.append(medication_row.id)
        yield NormalizedMedicationResult(
            id=medication_row.id,
            raw_text=entry.raw_text,
            name=name,
            rxcui=rxcui,
            dose=entry.dose,
            route=entry.route,
            frequency=entry.frequency,
        )

    findings = await find_interactions(
        normalized, session=session, openfda_client=openfda_ddi_client
    )
    for finding in findings:
        medication_a_id = persisted_ids[finding.medication_a_index]
        medication_b_id = persisted_ids[finding.medication_b_index]
        finding_row = await medication_repo.create_finding(
            chat_id=chat_id,
            medication_a_id=medication_a_id,
            medication_b_id=medication_b_id,
            type=FindingType.INTERACTION,
            severity=finding.severity,
            source=finding.source,
            rule_id=finding.rule_id,
            explanation=finding.explanation,
            provenance=finding.provenance,
        )
        yield InteractionFindingResult(
            id=finding_row.id,
            medication_a_id=medication_a_id,
            medication_b_id=medication_b_id,
            severity=finding.severity.value,
            source=finding.source.value,
            rule_id=finding.rule_id,
            explanation=finding.explanation,
            provenance=finding.provenance,
        )

    if renal_params is not None:
        for renal_finding in check_renal_thresholds(normalized, renal_params):
            medication_id = persisted_ids[renal_finding.medication_index]
            renal_row = await medication_repo.create_finding(
                chat_id=chat_id,
                medication_a_id=medication_id,
                medication_b_id=None,
                type=FindingType.RENAL,
                severity=renal_finding.severity,
                source=InteractionSource.CALCULATED,
                rule_id=renal_finding.rule_id,
                explanation=renal_finding.explanation,
                provenance={
                    "crcl_ml_min": renal_finding.crcl_ml_min,
                    "egfr_ml_min": renal_finding.egfr_ml_min,
                    "threshold_ml_min": renal_finding.threshold_ml_min,
                },
            )
            yield RenalFindingResult(
                id=renal_row.id,
                medication_id=medication_id,
                crcl_ml_min=renal_finding.crcl_ml_min,
                egfr_ml_min=renal_finding.egfr_ml_min,
                threshold_ml_min=renal_finding.threshold_ml_min,
                severity=renal_finding.severity.value,
                rule_id=renal_finding.rule_id,
                explanation=renal_finding.explanation,
            )
