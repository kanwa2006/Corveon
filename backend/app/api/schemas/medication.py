"""Medication-Safety Engine request/SSE-event schemas (docs/API.md —
Evidence & medication, blueprint §9). Normalization + DDI detection
(Phase 1) and renal/dose checks (Phase 2, ADR-0005) — no ``pip_flags``/
``discrepancies`` fields yet, those are later Medication-Safety Engine
phases."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.validation import reject_nul_bytes
from app.medication.renal import RenalParameters

_RENAL_PARAM_FIELDS = (
    "age_years",
    "weight_kg",
    "sex",
    "serum_creatinine_mg_dl",
    "height_cm",
)


class MedicationAnalyzeRequest(BaseModel):
    """Free text describing one or more medications (a discharge-summary
    line, a patient-reported list, etc.) — the normalizer parses it into
    structured entries (blueprint §9's "ingestion" step). Renal parameters
    are optional — omitting all of them skips renal checks entirely (an
    honest "insufficient data" state, ADR-0005); supplying only some of
    them is rejected rather than silently skipped, since a partial set
    would otherwise fail quietly with no explanation."""

    raw_text: str = Field(min_length=1, max_length=10_000)
    age_years: int | None = Field(default=None, ge=0, le=120)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    sex: Literal["male", "female"] | None = None
    serum_creatinine_mg_dl: float | None = Field(default=None, gt=0, le=30)
    height_cm: float | None = Field(default=None, gt=0, le=272)

    _reject_nul_bytes = field_validator("raw_text")(reject_nul_bytes)

    @model_validator(mode="after")
    def _renal_params_all_or_nothing(self) -> MedicationAnalyzeRequest:
        provided = [getattr(self, name) is not None for name in _RENAL_PARAM_FIELDS]
        if any(provided) and not all(provided):
            raise ValueError(
                "Renal parameters must be provided together "
                f"({', '.join(_RENAL_PARAM_FIELDS)}) or omitted entirely."
            )
        return self

    @property
    def has_renal_parameters(self) -> bool:
        return self.age_years is not None

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
    ready rather than waiting for the whole list to finish."""

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


class MedicationAnalysisDoneEvent(BaseModel):
    status: str = "succeeded"
