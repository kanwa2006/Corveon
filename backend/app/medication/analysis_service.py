"""Medication-Safety Engine analysis service (blueprint §9) — Phase 1: given
free text describing a patient's medications, parses it into structured
entries, normalizes each to RxCUI via RxNorm, persists them, then runs the
deterministic DDI rules engine and persists its findings. An async
generator yielding one item per completed medication (as it's normalized/
persisted) and then one item per interaction finding, so the API layer can
stream results as they're ready rather than waiting for the whole analysis
to finish — same incremental-streaming shape as
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

from app.data.models.medication import FindingType
from app.data.repositories.medication_repository import MedicationRepository
from app.medication.interactions import (
    NormalizedMedication,
    SupportsCheckPair,
    find_interactions,
)
from app.medication.normalizer import normalize_entry, parse_medication_entries
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


async def run_medication_analysis(
    *,
    chat_id: uuid.UUID,
    raw_text: str,
    provider_registry: ProviderRegistry,
    rxnorm_client: SupportsNormalize,
    openfda_ddi_client: SupportsCheckPair,
    session: AsyncSession,
    medication_repo: MedicationRepository,
    max_llm_calls: int,
) -> AsyncIterator[NormalizedMedicationResult | InteractionFindingResult]:
    """Yields a ``NormalizedMedicationResult`` per parsed-and-persisted
    medication, then an ``InteractionFindingResult`` per DDI finding.
    Exactly one LLM call total (free-text parsing) — normalization and
    interaction detection are both fully deterministic, so this stays well
    within the per-request budget regardless of medication-list length.

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
