"""Medication-Safety Engine request/SSE-event schemas (docs/API.md —
Evidence & medication, blueprint §9). Normalization + DDI detection
(Phase 1), renal/dose checks (Phase 2, ADR-0005), and PIP screening
(Beers 2023 + STOPP/START v3) + discrepancy classification (Phase 3,
ADR-0019)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.validation import reject_nul_bytes
from app.medication.renal import RenalParameters

# weight_kg/sex/serum_creatinine_mg_dl/height_cm are all-or-nothing among
# themselves; age_years is shared with PIP screening (which needs no other
# renal field) so it is validated separately below, not folded into this
# group.
_RENAL_ONLY_FIELDS = ("weight_kg", "sex", "serum_creatinine_mg_dl", "height_cm")

_MAX_CONDITIONS = 20


def _reject_nul_bytes_in_list(values: list[str]) -> list[str]:
    for value in values:
        reject_nul_bytes(value)
    return values


class MedicationAnalyzeRequest(BaseModel):
    """Free text describing one or more medications (a discharge-summary
    line, a patient-reported list, etc.) — the normalizer parses it into
    structured entries (blueprint §9's "ingestion" step).

    Renal parameters (``weight_kg``/``sex``/``serum_creatinine_mg_dl``/
    ``height_cm``, plus ``age_years``) are optional — omitting all of them
    skips renal checks entirely (an honest "insufficient data" state,
    ADR-0005); supplying only some of the four renal-only fields is
    rejected rather than silently skipped. ``age_years`` alone (with
    ``conditions`` optional) is sufficient to trigger PIP screening
    (Beers 2023 + STOPP/START v3, ADR-0019) independent of whether renal
    checks are also requested. ``previous_raw_text``, when supplied,
    triggers discrepancy classification (ADR-0019) against ``raw_text``."""

    raw_text: str = Field(min_length=1, max_length=10_000)
    age_years: int | None = Field(default=None, ge=0, le=120)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    sex: Literal["male", "female"] | None = None
    serum_creatinine_mg_dl: float | None = Field(default=None, gt=0, le=30)
    height_cm: float | None = Field(default=None, gt=0, le=272)
    conditions: list[str] = Field(default_factory=list, max_length=_MAX_CONDITIONS)
    previous_raw_text: str | None = Field(default=None, max_length=10_000)

    _reject_nul_bytes = field_validator("raw_text", "previous_raw_text")(reject_nul_bytes)
    _reject_nul_bytes_conditions = field_validator("conditions")(_reject_nul_bytes_in_list)

    @model_validator(mode="after")
    def _renal_only_fields_all_or_nothing(self) -> MedicationAnalyzeRequest:
        provided = [getattr(self, name) is not None for name in _RENAL_ONLY_FIELDS]
        if any(provided):
            if not all(provided):
                raise ValueError(
                    "Renal parameters must be provided together "
                    f"({', '.join(_RENAL_ONLY_FIELDS)}) or omitted entirely."
                )
            if self.age_years is None:
                raise ValueError("age_years is required together with the other renal parameters.")
        return self

    @property
    def has_renal_parameters(self) -> bool:
        return self.weight_kg is not None

    @property
    def has_pip_screening(self) -> bool:
        return self.age_years is not None

    @property
    def has_discrepancy_check(self) -> bool:
        return bool(self.previous_raw_text and self.previous_raw_text.strip())

    def renal_parameters(self) -> RenalParameters | None:
        """Builds a ``RenalParameters`` when the request supplied one,
        narrowing the individually-optional fields in one place rather
        than scattering ``assert``s at every call site — the "all or
        nothing" model validator already guarantees these are non-None
        together."""
        if (
            self.age_years is None
            or self.weight_kg is None
            or self.sex is None
            or self.serum_creatinine_mg_dl is None
            or self.height_cm is None
        ):
            return None
        return RenalParameters(
            age_years=self.age_years,
            weight_kg=self.weight_kg,
            sex=self.sex,
            serum_creatinine_mg_dl=self.serum_creatinine_mg_dl,
            height_cm=self.height_cm,
        )


class MedicationEvent(BaseModel):
    """Payload of the SSE ``medication`` event — one parsed, RxNorm-
    normalized, already-persisted medication, streamed as soon as it's
    ready rather than waiting for the whole list to finish. Also reused,
    unchanged, for the SSE ``previous_medication`` event (Phase 3): the
    event name alone distinguishes which list an entry belongs to when
    ``previous_raw_text`` triggers discrepancy classification."""

    id: uuid.UUID
    raw_text: str
    name: str
    rxcui: str | None
    dose: str | None
    route: str | None
    frequency: str | None


class InteractionFindingEvent(BaseModel):
    """Payload of the SSE ``interaction`` event — one deterministic DDI
    rules-engine finding, streamed once all medications are normalized and
    every pair has been checked."""

    id: uuid.UUID
    medication_a_id: uuid.UUID
    medication_b_id: uuid.UUID
    severity: str
    source: str
    rule_id: str
    explanation: str
    provenance: dict[str, Any]


class RenalFindingEvent(BaseModel):
    """Payload of the SSE ``renal`` event — one deterministic renal-dosing
    threshold finding (Cockcroft-Gault + CKD-EPI 2021, ADR-0005), streamed
    after interaction findings once both equations have been checked
    against every threshold-sensitive medication. Only emitted when the
    request supplied renal parameters."""

    id: uuid.UUID
    medication_id: uuid.UUID
    crcl_ml_min: float
    egfr_ml_min: float
    threshold_ml_min: float
    severity: str
    rule_id: str
    explanation: str


class PipFindingEvent(BaseModel):
    """Payload of the SSE ``pip`` event — one deterministic potentially-
    inappropriate-prescribing finding (Beers 2023 / STOPP/START v3,
    ADR-0019), streamed after renal findings once every pinned criterion
    has been checked. Only emitted when the request supplied ``age_years``
    (``has_pip_screening``) and the patient is ≥65. ``medication_id`` is
    null for a START-criterion finding — it flags a medication *missing*
    from the current list, not one present in it. ``narrative`` is a
    guardrail-checked plain-language rendering of ``explanation``
    (ADR-0020); null when no provider was available, the budget was
    exhausted, or the generated text failed the grounding check — the
    deterministic ``explanation`` is always present regardless."""

    id: uuid.UUID
    medication_id: uuid.UUID | None
    source: str
    direction: str
    severity: str
    rule_id: str
    drug_names: list[str]
    matched_condition: str | None
    explanation: str
    narrative: str | None = None


class DiscrepancyFindingEvent(BaseModel):
    """Payload of the SSE ``discrepancy`` event — one deterministic
    medication-list diff finding (ADR-0019), streamed after PIP findings.
    Only emitted when the request supplied ``previous_raw_text``.
    ``current_medication_id``/``previous_medication_id`` are each null when
    the finding has no counterpart in that list (``added``/``omitted``).
    ``narrative`` follows the same guardrail-checked, nullable convention
    as ``PipFindingEvent.narrative`` (ADR-0020)."""

    id: uuid.UUID
    kind: str
    current_medication_id: uuid.UUID | None
    previous_medication_id: uuid.UUID | None
    rule_id: str
    explanation: str
    narrative: str | None = None
    provenance: dict[str, Any]


class MedicationAnalysisDoneEvent(BaseModel):
    status: str = "succeeded"
