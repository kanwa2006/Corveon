"""Message endpoints — SSE-streaming grounded chat (docs/API.md — Messages/AI,
ADR-0007). ``POST`` is 202 + SSE: ``token`` events carry text deltas as they
stream, a final ``done`` event carries the persisted assistant message id and
routing_trace, or an ``error`` event if no provider is currently reachable
(degraded mode, ADR-0006) — never a bare HTTP failure once streaming starts."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import (
    CurrentUserDep,
    EmbeddingModelDep,
    EvidenceConnectorRegistryDep,
    ProviderRegistryDep,
    RlsDbDep,
    SettingsDep,
    StreamingRlsDbDep,
    StreamingUserDep,
)
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.message import DoneEvent, ExportRequest, MessageCreateRequest, MessagePublic
from app.core.errors import NotFoundError
from app.data.models.message import Message, MessageRole
from app.data.repositories.audit_log_repository import AuditLogRepository
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.repositories.message_repository import MessageRepository
from app.data.rls import commit_and_reapply_rls
from app.data.vectorstore.registry import build_vector_store
from app.export.message_export import render
from app.orchestrator.chat_orchestrator import stream_response
from app.providers.base import ChatMessage, ChatRole
from app.providers.budget import LLMCallBudgetExceededError
from app.providers.registry import NoProviderAvailableError

router = APIRouter(prefix="/chats", tags=["messages"])


def _to_chat_message(message: Message) -> ChatMessage:
    role = ChatRole.ASSISTANT if message.role == MessageRole.ASSISTANT else ChatRole.USER
    return ChatMessage(role=role, content=message.content)


@router.get("/{chat_id}/messages", response_model=list[MessagePublic])
async def list_messages(
    chat_id: uuid.UUID, db: RlsDbDep, current_user: CurrentUserDep
) -> list[MessagePublic]:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)
    message_repo = MessageRepository(db)
    messages = await message_repo.list_for_chat(chat_id)
    return [MessagePublic.model_validate(message) for message in messages]


@router.post("/{chat_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    chat_id: uuid.UUID,
    payload: MessageCreateRequest,
    db: StreamingRlsDbDep,
    current_user: StreamingUserDep,
    embedding_model: EmbeddingModelDep,
    provider_registry: ProviderRegistryDep,
    evidence_registry: EvidenceConnectorRegistryDep,
    settings: SettingsDep,
) -> EventSourceResponse:
    # The browser connects to this endpoint directly (ADR-0007), so it
    # authenticates via a short-lived stream ticket rather than the httpOnly
    # session cookie (StreamingUserDep/StreamingRlsDbDep, ADR-0012).
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    message_repo = MessageRepository(db)
    chunk_repo = ChunkRepository(db, build_vector_store(settings, db))

    await message_repo.create(chat_id=chat_id, role=MessageRole.USER, content=payload.content)
    # set_config(..., true) is transaction-local (ADR-0013) — this commit
    # would otherwise silently reset the RLS GUC for every query/write below.
    await commit_and_reapply_rls(db, current_user.id)

    history = [_to_chat_message(m) for m in await message_repo.list_for_chat(chat_id)]

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            async for delta in stream_response(
                provider_registry=provider_registry,
                chunk_repo=chunk_repo,
                message_repo=message_repo,
                embedding_model=embedding_model,
                evidence_registry=evidence_registry,
                chat_id=chat_id,
                history=history,
                user_query=payload.content,
                max_llm_calls=settings.LLM_CALLS_PER_REQUEST_BUDGET,
            ):
                yield {"event": "token", "data": delta}
            await commit_and_reapply_rls(db, current_user.id)
            assistant_message = (await message_repo.list_for_chat(chat_id))[-1]
            yield {
                "event": "done",
                "data": DoneEvent(
                    message_id=assistant_message.id,
                    routing_trace=assistant_message.routing_trace,
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
                '"message": "This request exceeded its LLM call budget."}',
            }

    # FastAPI's route-decorator status_code only governs responses it builds
    # itself from a returned model; a Response subclass returned directly
    # (EventSourceResponse here) must set its own status_code or it defaults
    # to 200 — docs/API.md specifies 202 for this endpoint.
    return EventSourceResponse(event_stream(), status_code=status.HTTP_202_ACCEPTED)


@router.post("/{chat_id}/messages/{message_id}/export")
async def export_message(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ExportRequest,
    request: Request,
    db: RlsDbDep,
    current_user: CurrentUserDep,
) -> Response:
    """Renders a single message (with its citations and routing metadata) to
    Markdown or PDF — synchronous, per docs/API.md (`200` file, not a job)."""
    chat_repo = ChatRepository(db)
    chat = await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    message_repo = MessageRepository(db)
    message = await message_repo.get_by_id_for_chat(message_id, chat_id)
    if message is None:
        raise NotFoundError("Message not found.")

    data, media_type, filename = render(
        export_format=payload.format, chat_title=chat.title, message=message
    )
    await AuditLogRepository(db).create(
        actor_id=current_user.id,
        action="message.export",
        entity_type="message",
        entity_id=message.id,
        ip=request.client.host if request.client else None,
        metadata={"chat_id": str(chat_id), "format": payload.format.value},
    )
    await db.commit()
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
