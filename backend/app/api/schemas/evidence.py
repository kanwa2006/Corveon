"""Evidence Verification request/SSE-event schemas (docs/API.md — Evidence
verification, blueprint §13)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from app.data.models.evidence import VerificationStatus


class VerifyRequest(BaseModel):
    """Verifies the claims in one existing message — the natural unit for
    "check this AI response" or "check what this uploaded-PDF summary
    claims" (blueprint §3.2's own worked example)."""

    message_id: uuid.UUID


class ClaimEvent(BaseModel):
    """Payload of the SSE ``claim`` event — one completed, already-scored
    claim, streamed as soon as it's ready rather than waiting for every
    claim in the message to finish."""

    id: uuid.UUID
    ordinal: int
    text: str
    source_class: str
    confidence_score: int
    confidence_rationale: str
    flags: list[dict[str, str]]
    citations: list[dict[str, Any]]


class VerificationDoneEvent(BaseModel):
    verification_id: uuid.UUID
    status: VerificationStatus
