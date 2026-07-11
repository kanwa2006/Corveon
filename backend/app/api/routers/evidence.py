"""Evidence Verification endpoint (docs/API.md — Evidence verification,
blueprint §13). ``POST`` is 202 + SSE: a ``claim`` event per completed,
already-scored claim (streamed as it's ready, not batched), a final
``done`` event, or an ``error`` event on a degraded-mode condition — same
shape as ``POST /chats/{id}/messages`` (ADR-0007: the browser connects to
this endpoint directly for SSE, authenticating via a stream ticket)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import (
    EmbeddingModelDep,
    EvidenceConnectorRegistryDep,
    ProviderRegistryDep,
    SettingsDep,
    StreamingRlsDbDep,
    StreamingUserDep,
)
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.evidence import ClaimEvent, VerificationDoneEvent, VerifyRequest
from app.core.errors import NotFoundError
from app.data.models.evidence import VerificationStatus
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.repositories.evidence_repository import EvidenceRepository
from app.data.repositories.message_repository import MessageRepository
from app.data.rls import commit_and_reapply_rls
from app.data.vectorstore.registry import build_vector_store
from app.evidence.verification_service import run_verification
from app.providers.budget import LLMCallBudgetExceededError
from app.providers.registry import NoProviderAvailableError

router = APIRouter(prefix="/chats", tags=["evidence"])


@router.post("/{chat_id}/verify", status_code=status.HTTP_202_ACCEPTED)
async def verify_message(
    chat_id: uuid.UUID,
    payload: VerifyRequest,
    request: Request,
    db: StreamingRlsDbDep,
    current_user: StreamingUserDep,
    embedding_model: EmbeddingModelDep,
    provider_registry: ProviderRegistryDep,
    connector_registry: EvidenceConnectorRegistryDep,
    settings: SettingsDep,
) -> EventSourceResponse:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    message_repo = MessageRepository(db)
    message = await message_repo.get_by_id_for_chat(payload.message_id, chat_id)
    if message is None:
        raise NotFoundError("Message not found.")

    evidence_repo = EvidenceRepository(db)
    verification = await evidence_repo.create_verification(chat_id=chat_id, message_id=message.id)
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="evidence.verify",
        entity_type="evidence_verification",
        entity_id=verification.id,
        ip=request.client.host if request.client else None,
        metadata={"chat_id": str(chat_id), "message_id": str(message.id)},
    )
    # set_config(..., true) is transaction-local (ADR-0013) — this commit
    # would otherwise silently reset the RLS GUC for every query/write below.
    await commit_and_reapply_rls(db, current_user.id)

    chunk_repo = ChunkRepository(db, build_vector_store(settings, db))

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            async for claim in run_verification(
                chat_id=chat_id,
                verification_id=verification.id,
                message_text=message.content,
                provider_registry=provider_registry,
                connector_registry=connector_registry,
                chunk_repo=chunk_repo,
                embedding_model=embedding_model,
                evidence_repo=evidence_repo,
                max_llm_calls=settings.LLM_CALLS_PER_REQUEST_BUDGET,
            ):
                await commit_and_reapply_rls(db, current_user.id)
                yield {
                    "event": "claim",
                    "data": ClaimEvent(
                        id=claim.id,
                        ordinal=claim.ordinal,
                        text=claim.text,
                        source_class=claim.source_class,
                        confidence_score=claim.confidence_score,
                        confidence_rationale=claim.confidence_rationale,
                        flags=claim.flags,
                        citations=[c.as_dict() for c in claim.citations],
                    ).model_dump_json(),
                }
            await db.commit()
            yield {
                "event": "done",
                "data": VerificationDoneEvent(
                    verification_id=verification.id, status=VerificationStatus.SUCCEEDED
                ).model_dump_json(),
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
                '"message": "This verification exceeded its LLM call budget."}',
            }

    # See messages.py's identical note: EventSourceResponse must set its own
    # status_code, the route decorator's only governs FastAPI-built responses.
    return EventSourceResponse(event_stream(), status_code=status.HTTP_202_ACCEPTED)
