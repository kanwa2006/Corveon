"""Medication-Safety Engine analysis service (blueprint §9) — given free
text describing a patient's medications, parses it into structured
entries, normalizes each to RxCUI via RxNorm, persists them, then runs the
deterministic DDI rules engine (Phase 1); when renal parameters are
supplied, the renal-dosing threshold checks (Phase 2, ADR-0005); when
``age_years`` is supplied, PIP screening (Beers 2023 + STOPP/START v3,
Phase 3, ADR-0019); and when ``previous_raw_text`` is supplied, medication-
discrepancy classification against a second, independently parsed and
normalized list (Phase 3, ADR-0019) — persisting findings as they're
produced. PIP and discrepancy findings additionally get one batched,
guardrail-checked LLM narrative pass (ADR-0020). An async generator
yielding one item per completed medication (current list, then previous
list if supplied), then interaction findings, then renal findings, then PIP
findings, then discrepancy findings, so the API layer can stream results as
they're ready rather than waiting for the whole analysis to finish — same
incremental-streaming shape as app/evidence/verification_service.py.

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

from app.data.models.medication import FindingSeverity, FindingType, InteractionSource
from app.data.repositories.medication_repository import MedicationRepository
from app.medication.discrepancy import DiscrepancyFinding, classify_discrepancies
from app.medication.explanation_guardrail import NarrativeFact, generate_grounded_narratives
from app.medication.interactions import (
    NormalizedMedication,
    SupportsCheckPair,
    find_interactions,
)
from app.medication.normalizer import normalize_entry, parse_medication_entries
from app.medication.pip_screening import PipFinding, check_pip_criteria
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
    # True for an entry from `previous_raw_text` (Phase 3 discrepancy
    # classification) — the router uses this to choose between the SSE
    # `medication` and `previous_medication` event names; the payload
    # shape itself is identical either way.
    is_previous: bool = False

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


@dataclass(frozen=True, slots=True)
class PipFindingResult:
    id: uuid.UUID
    # None for a START-criterion finding — it flags a medication missing
    # from the current list, not one present in it (ADR-0019).
    medication_id: uuid.UUID | None
    source: str
    direction: str
    severity: str
    rule_id: str
    drug_names: list[str]
    matched_condition: str | None
    explanation: str
    narrative: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "medication_id": str(self.medication_id) if self.medication_id else None,
            "source": self.source,
            "direction": self.direction,
            "severity": self.severity,
            "rule_id": self.rule_id,
            "drug_names": self.drug_names,
            "matched_condition": self.matched_condition,
            "explanation": self.explanation,
            "narrative": self.narrative,
        }


@dataclass(frozen=True, slots=True)
class DiscrepancyFindingResult:
    id: uuid.UUID
    kind: str
    current_medication_id: uuid.UUID | None
    previous_medication_id: uuid.UUID | None
    rule_id: str
    explanation: str
    narrative: str | None
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "kind": self.kind,
            "current_medication_id": (
                str(self.current_medication_id) if self.current_medication_id else None
            ),
            "previous_medication_id": (
                str(self.previous_medication_id) if self.previous_medication_id else None
            ),
            "rule_id": self.rule_id,
            "explanation": self.explanation,
            "narrative": self.narrative,
            "provenance": self.provenance,
        }


async def _parse_normalize_and_persist(
    *,
    chat_id: uuid.UUID,
    raw_text: str,
    is_previous: bool,
    provider_registry: ProviderRegistry,
    rxnorm_client: SupportsNormalize,
    medication_repo: MedicationRepository,
    budget: LLMCallBudget,
) -> AsyncIterator[tuple[NormalizedMedication, uuid.UUID, NormalizedMedicationResult]]:
    entries = await parse_medication_entries(
        provider_registry=provider_registry, text=raw_text, budget=budget
    )
    for entry in entries:
        rxcui, name, match_names = await normalize_entry(entry, rxnorm_client=rxnorm_client)
        medication_row = await medication_repo.create_medication(
            chat_id=chat_id,
            raw_text=entry.raw_text,
            name=name,
            rxcui=rxcui,
            dose=entry.dose,
            route=entry.route,
            frequency=entry.frequency,
        )
        normalized = NormalizedMedication(
            raw_text=entry.raw_text,
            name=name,
            rxcui=rxcui,
            dose=entry.dose,
            route=entry.route,
            frequency=entry.frequency,
            match_names=match_names,
        )
        yield (
            normalized,
            medication_row.id,
            NormalizedMedicationResult(
                id=medication_row.id,
                raw_text=entry.raw_text,
                name=name,
                rxcui=rxcui,
                dose=entry.dose,
                route=entry.route,
                frequency=entry.frequency,
                is_previous=is_previous,
            ),
        )


async def run_medication_analysis(
    *,
    chat_id: uuid.UUID,
    raw_text: str,
    renal_params: RenalParameters | None,
    age_years: int | None,
    conditions: list[str],
    previous_raw_text: str | None,
    provider_registry: ProviderRegistry,
    rxnorm_client: SupportsNormalize,
    openfda_ddi_client: SupportsCheckPair,
    session: AsyncSession,
    medication_repo: MedicationRepository,
    max_llm_calls: int,
) -> AsyncIterator[
    NormalizedMedicationResult
    | InteractionFindingResult
    | RenalFindingResult
    | PipFindingResult
    | DiscrepancyFindingResult
]:
    """Yields a ``NormalizedMedicationResult`` per parsed-and-persisted
    current-list medication, then (only when ``previous_raw_text`` is
    given) one per previous-list medication, then an
    ``InteractionFindingResult`` per DDI finding (current list only), then
    — only when ``renal_params`` is given — a ``RenalFindingResult`` per
    threshold-sensitive medication, then — only when ``age_years`` is given
    and the patient is ≥65 — a ``PipFindingResult`` per Beers 2023/STOPP-
    START v3 match, then — only when ``previous_raw_text`` is given — a
    ``DiscrepancyFindingResult`` per added/omitted/changed medication.

    LLM calls: one for the current list's free-text parse, one more when
    ``previous_raw_text`` is given (a second, independent parse), and at
    most one more batched call to generate guardrail-checked narratives for
    any PIP/discrepancy findings (ADR-0020) — all against the same
    ``max_llm_calls`` budget, regardless of medication-list length.

    Raises ``NoProviderAvailableError``/``LLMCallBudgetExceededError`` when
    a *required* parse fails — propagated to the caller unchanged, same
    division of responsibility as verification_service.run_verification.
    The optional narrative-generation call degrades silently instead (see
    app/medication/explanation_guardrail.py)."""
    budget = LLMCallBudget(max_llm_calls)

    normalized: list[NormalizedMedication] = []
    persisted_ids: list[uuid.UUID] = []
    async for item, medication_id, result in _parse_normalize_and_persist(
        chat_id=chat_id,
        raw_text=raw_text,
        is_previous=False,
        provider_registry=provider_registry,
        rxnorm_client=rxnorm_client,
        medication_repo=medication_repo,
        budget=budget,
    ):
        normalized.append(item)
        persisted_ids.append(medication_id)
        yield result

    previous_normalized: list[NormalizedMedication] = []
    previous_persisted_ids: list[uuid.UUID] = []
    if previous_raw_text is not None and previous_raw_text.strip():
        async for item, medication_id, result in _parse_normalize_and_persist(
            chat_id=chat_id,
            raw_text=previous_raw_text,
            is_previous=True,
            provider_registry=provider_registry,
            rxnorm_client=rxnorm_client,
            medication_repo=medication_repo,
            budget=budget,
        ):
            previous_normalized.append(item)
            previous_persisted_ids.append(medication_id)
            yield result

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

    pip_findings: list[PipFinding] = []
    if age_years is not None:
        pip_findings = await check_pip_criteria(
            normalized, age_years=age_years, conditions=conditions, session=session
        )

    discrepancy_findings: list[DiscrepancyFinding] = []
    if previous_normalized or (previous_raw_text is not None and previous_raw_text.strip()):
        discrepancy_findings = classify_discrepancies(previous_normalized, normalized)

    narratives: dict[str, str] = {}
    if pip_findings or discrepancy_findings:
        all_drug_names = {m.name for m in normalized} | {m.name for m in previous_normalized}
        facts = [
            NarrativeFact(
                key=f"pip:{index}",
                drug_names=finding.drug_names,
                severity=finding.severity.value,
                rationale=finding.explanation,
                recommendation=finding.explanation,
                explanation=finding.explanation,
            )
            for index, finding in enumerate(pip_findings)
        ] + [
            NarrativeFact(
                key=f"discrepancy:{index}",
                drug_names=[finding.provenance.get("name", "")],
                severity="unclassified",
                rationale=finding.explanation,
                recommendation=finding.explanation,
                explanation=finding.explanation,
            )
            for index, finding in enumerate(discrepancy_findings)
        ]
        narratives = await generate_grounded_narratives(
            facts, all_drug_names=all_drug_names, provider_registry=provider_registry, budget=budget
        )

    for index, pip_finding in enumerate(pip_findings):
        pip_medication_id = (
            persisted_ids[pip_finding.medication_index]
            if pip_finding.medication_index is not None
            else None
        )
        pip_row = await medication_repo.create_finding(
            chat_id=chat_id,
            medication_a_id=pip_medication_id,
            medication_b_id=None,
            type=FindingType.PIP,
            severity=pip_finding.severity,
            source=InteractionSource.CALCULATED,
            rule_id=pip_finding.rule_id,
            explanation=pip_finding.explanation,
            provenance={
                "source": pip_finding.source.value,
                "direction": pip_finding.direction.value,
                "drug_names": pip_finding.drug_names,
                "matched_condition": pip_finding.matched_condition,
            },
        )
        yield PipFindingResult(
            id=pip_row.id,
            medication_id=pip_medication_id,
            source=pip_finding.source.value,
            direction=pip_finding.direction.value,
            severity=pip_finding.severity.value,
            rule_id=pip_finding.rule_id,
            drug_names=pip_finding.drug_names,
            matched_condition=pip_finding.matched_condition,
            explanation=pip_finding.explanation,
            narrative=narratives.get(f"pip:{index}"),
        )

    for index, discrepancy_finding in enumerate(discrepancy_findings):
        current_medication_id = (
            persisted_ids[discrepancy_finding.current_index]
            if discrepancy_finding.current_index is not None
            else None
        )
        previous_medication_id = (
            previous_persisted_ids[discrepancy_finding.previous_index]
            if discrepancy_finding.previous_index is not None
            else None
        )
        # discrepancy_medication_a_id is "the" medication for this finding
        # regardless of which list it came from (current when present,
        # else previous) — same convention documented on MedicationFinding.
        discrepancy_medication_a_id = current_medication_id or previous_medication_id
        discrepancy_medication_b_id = previous_medication_id if current_medication_id else None
        discrepancy_row = await medication_repo.create_finding(
            chat_id=chat_id,
            medication_a_id=discrepancy_medication_a_id,
            medication_b_id=discrepancy_medication_b_id,
            type=FindingType.DISCREPANCY,
            severity=FindingSeverity.UNCLASSIFIED,
            source=InteractionSource.CALCULATED,
            rule_id=discrepancy_finding.rule_id,
            explanation=discrepancy_finding.explanation,
            provenance=discrepancy_finding.provenance,
        )
        yield DiscrepancyFindingResult(
            id=discrepancy_row.id,
            kind=discrepancy_finding.kind,
            current_medication_id=current_medication_id,
            previous_medication_id=previous_medication_id,
            rule_id=discrepancy_finding.rule_id,
            explanation=discrepancy_finding.explanation,
            narrative=narratives.get(f"discrepancy:{index}"),
            provenance=discrepancy_finding.provenance,
        )
