"""Medication-Safety Engine request/SSE-event schemas (docs/API.md —
Evidence & medication, blueprint §9). Phase 1 only: normalization + DDI
detection — no ``renal``/``pip_flags``/``discrepancies`` fields yet, those
are later Medication-Safety Engine phases."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MedicationAnalyzeRequest(BaseModel):
    """Free text describing one or more medications (a discharge-summary
    line, a patient-reported list, etc.) — the normalizer parses it into
    structured entries (blueprint §9's "ingestion" step)."""

    raw_text: str = Field(min_length=1, max_length=10_000)

    @field_validator("raw_text")
    @classmethod
    def _reject_nul_bytes(cls, value: str) -> str:
        # Postgres text columns reject an embedded NUL byte at the wire
        # level (asyncpg CharacterNotInRepertoireError) — must surface as a
        # 422 here, not an uncaught 500 from the DB driver later (the exact
        # bug fixed in PATCH /chats/{id}, applied proactively here since
        # this field is stored the same way).
        if "\x00" in value:
            raise ValueError("raw_text must not contain NUL bytes.")
        return value


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
