"""Medication-Safety Engine repository (Phase 1). Every chat-scoped query is
scoped by chat_id — the isolation anchor (docs/ARCHITECTURE.md §5) — same
invariant every other content repository in this codebase enforces."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.medication import (
    FindingSeverity,
    FindingType,
    InteractionSource,
    Medication,
    MedicationFinding,
)


class MedicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_medication(
        self,
        *,
        chat_id: uuid.UUID,
        raw_text: str,
        name: str,
        rxcui: str | None = None,
        dose: str | None = None,
        route: str | None = None,
        frequency: str | None = None,
    ) -> Medication:
        medication = Medication(
            chat_id=chat_id,
            raw_text=raw_text,
            name=name,
            rxcui=rxcui,
            dose=dose,
            route=route,
            frequency=frequency,
        )
        self._session.add(medication)
        await self._session.flush()
        return medication

    async def create_finding(
        self,
        *,
        chat_id: uuid.UUID,
        medication_a_id: uuid.UUID | None,
        medication_b_id: uuid.UUID | None,
        type: FindingType,
        severity: FindingSeverity,
        source: InteractionSource,
        rule_id: str,
        explanation: str,
        provenance: dict[str, object] | None = None,
    ) -> MedicationFinding:
        finding = MedicationFinding(
            chat_id=chat_id,
            medication_a_id=medication_a_id,
            medication_b_id=medication_b_id,
            type=type,
            severity=severity,
            source=source,
            rule_id=rule_id,
            explanation=explanation,
            provenance=provenance or {},
        )
        self._session.add(finding)
        await self._session.flush()
        return finding

    async def list_medications_for_chat(self, chat_id: uuid.UUID) -> list[Medication]:
        result = await self._session.execute(
            select(Medication).where(Medication.chat_id == chat_id).order_by(Medication.created_at)
        )
        return list(result.scalars().all())

    async def list_findings_for_chat(self, chat_id: uuid.UUID) -> list[MedicationFinding]:
        result = await self._session.execute(
            select(MedicationFinding)
            .where(MedicationFinding.chat_id == chat_id)
            .order_by(MedicationFinding.created_at)
        )
        return list(result.scalars().all())
