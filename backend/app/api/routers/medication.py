"""Medication-Safety Engine endpoint (docs/API.md — Evidence & medication,
blueprint §9). Normalization + DDI detection (Phase 1), renal/dose checks
(Phase 2, ADR-0005), and PIP screening + discrepancy classification
(Phase 3, ADR-0019). ``POST`` is 202 + SSE: a ``medication`` event per
normalized/persisted current-list medication, a ``previous_medication``
event per previous-list medication (only when ``previous_raw_text`` is
supplied), an ``interaction`` event per DDI finding, a ``renal`` event per
renal-dosing threshold finding (only when the request supplied renal
parameters), a ``pip`` event per potentially-inappropriate-prescribing
finding (only when the request supplied ``age_years``), a ``discrepancy``
event per medication-list diff finding (only when the request supplied
``previous_raw_text``), a final ``done`` event, or an ``error`` event on a
degraded-mode condition — same shape as ``POST /chats/{id}/verify``
(ADR-0007: the browser connects to this endpoint directly for SSE,
authenticating via a stream ticket)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import (
    OpenFdaDdiClientDep,
    ProviderRegistryDep,
    RxNormClientDep,
    SettingsDep,
    StreamingRlsDbDep,
    StreamingUserDep,
)
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.medication import (
    DiscrepancyFindingEvent,
    InteractionFindingEvent,
    MedicationAnalysisDoneEvent,
    MedicationAnalyzeRequest,
    MedicationEvent,
    PipFindingEvent,
    RenalFindingEvent,
)
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.medication_repository import MedicationRepository
from app.data.rls import commit_and_reapply_rls
from app.medication.analysis_service import (
    InteractionFindingResult,
    NormalizedMedicationResult,
    PipFindingResult,
    RenalFindingResult,
    run_medication_analysis,
)
from app.providers.budget import LLMCallBudgetExceededError
from app.providers.registry import NoProviderAvailableError

router = APIRouter(prefix="/chats", tags=["medication"])


@router.post("/{chat_id}/medications/analyze", status_code=status.HTTP_202_ACCEPTED)
async def analyze_medications(
    chat_id: uuid.UUID,
    payload: MedicationAnalyzeRequest,
    request: Request,
    db: StreamingRlsDbDep,
    current_user: StreamingUserDep,
    provider_registry: ProviderRegistryDep,
    rxnorm_client: RxNormClientDep,
    openfda_ddi_client: OpenFdaDdiClientDep,
    settings: SettingsDep,
) -> EventSourceResponse:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="medication.analyze",
        entity_type="chat",
        entity_id=chat_id,
        ip=request.client.host if request.client else None,
        metadata={"chat_id": str(chat_id)},
    )
    # set_config(..., true) is transaction-local (ADR-0013) — this commit
    # would otherwise silently reset the RLS GUC for every query/write below.
    await commit_and_reapply_rls(db, current_user.id)

    medication_repo = MedicationRepository(db)
    renal_params = payload.renal_parameters()

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            async for item in run_medication_analysis(
                chat_id=chat_id,
                raw_text=payload.raw_text,
                renal_params=renal_params,
                age_years=payload.age_years,
                conditions=payload.conditions,
                previous_raw_text=payload.previous_raw_text,
                provider_registry=provider_registry,
                rxnorm_client=rxnorm_client,
                openfda_ddi_client=openfda_ddi_client,
                session=db,
                medication_repo=medication_repo,
                max_llm_calls=settings.LLM_CALLS_PER_REQUEST_BUDGET,
            ):
                await commit_and_reapply_rls(db, current_user.id)
                if isinstance(item, NormalizedMedicationResult):
                    yield {
                        "event": "previous_medication" if item.is_previous else "medication",
                        "data": MedicationEvent(
                            id=item.id,
                            raw_text=item.raw_text,
                            name=item.name,
                            rxcui=item.rxcui,
                            dose=item.dose,
                            route=item.route,
                            frequency=item.frequency,
                        ).model_dump_json(),
                    }
                elif isinstance(item, InteractionFindingResult):
                    yield {
                        "event": "interaction",
                        "data": InteractionFindingEvent(
                            id=item.id,
                            medication_a_id=item.medication_a_id,
                            medication_b_id=item.medication_b_id,
                            severity=item.severity,
                            source=item.source,
                            rule_id=item.rule_id,
                            explanation=item.explanation,
                            provenance=item.provenance,
                        ).model_dump_json(),
                    }
                elif isinstance(item, RenalFindingResult):
                    yield {
                        "event": "renal",
                        "data": RenalFindingEvent(
                            id=item.id,
                            medication_id=item.medication_id,
                            crcl_ml_min=item.crcl_ml_min,
                            egfr_ml_min=item.egfr_ml_min,
                            threshold_ml_min=item.threshold_ml_min,
                            severity=item.severity,
                            rule_id=item.rule_id,
                            explanation=item.explanation,
                        ).model_dump_json(),
                    }
                elif isinstance(item, PipFindingResult):
                    yield {
                        "event": "pip",
                        "data": PipFindingEvent(
                            id=item.id,
                            medication_id=item.medication_id,
                            source=item.source,
                            direction=item.direction,
                            severity=item.severity,
                            rule_id=item.rule_id,
                            drug_names=item.drug_names,
                            matched_condition=item.matched_condition,
                            explanation=item.explanation,
                            narrative=item.narrative,
                        ).model_dump_json(),
                    }
                else:
                    yield {
                        "event": "discrepancy",
                        "data": DiscrepancyFindingEvent(
                            id=item.id,
                            kind=item.kind,
                            current_medication_id=item.current_medication_id,
                            previous_medication_id=item.previous_medication_id,
                            rule_id=item.rule_id,
                            explanation=item.explanation,
                            narrative=item.narrative,
                            provenance=item.provenance,
                        ).model_dump_json(),
                    }
            await db.commit()
            yield {
                "event": "done",
                "data": MedicationAnalysisDoneEvent().model_dump_json(),
            }
        except NoProviderAvailableError:
            await db.commit()
            yield {
                "event": "error",
                "data": '{"error_code": "provider_unavailable", '
                '"message": "No AI provider is currently reachable."}',
            }
        except LLMCallBudgetExceededError:
            await db.commit()
            yield {
                "event": "error",
                "data": '{"error_code": "budget_exceeded", '
                '"message": "This analysis exceeded its LLM call budget."}',
            }

    # See messages.py's identical note: EventSourceResponse must set its own
    # status_code, the route decorator's only governs FastAPI-built responses.
    return EventSourceResponse(event_stream(), status_code=status.HTTP_202_ACCEPTED)
