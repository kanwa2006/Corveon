"""Medication-Safety Engine request/SSE-event schemas (docs/API.md —
Evidence & medication, blueprint §9). Phase 1 only: normalization + DDI
detection — no ``renal``/``pip_flags``/``discrepancies`` fields yet, those
are later Medication-Safety Engine phases."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.validation import reject_nul_bytes


class MedicationAnalyzeRequest(BaseModel):
    """Free text describing one or more medications (a discharge-summary
    line, a patient-reported list, etc.) — the normalizer parses it into
    structured entries (blueprint §9's "ingestion" step)."""

    raw_text: str = Field(min_length=1, max_length=10_000)

    _reject_nul_bytes = field_validator("raw_text")(reject_nul_bytes)


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


class MedicationAnalysisDoneEvent(BaseModel):
    status: str = "succeeded"
