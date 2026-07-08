"""Job status + progress-events endpoints (docs/API.md — Documents/uploads,
ADR-0007: SSE served by the backend). Progress is observed by polling the job
row the worker updates at each pipeline stage (app/workers/tasks.py) — simple
and reliable for a solo-dev MVP; no separate pub/sub channel needed yet."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api.deps import CurrentUserDep, RlsDbDep, StreamingRlsDbDep, StreamingUserDep
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.document import JobPublic
from app.core.errors import NotFoundError
from app.data.models.job import Job, JobStatus
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.job_repository import JobRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])

_POLL_INTERVAL_SECONDS = 0.5
_TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED}


async def _get_owned_job_or_404(
    job_repo: JobRepository, chat_repo: ChatRepository, job_id: uuid.UUID, user_id: uuid.UUID
) -> Job:
    # Flat resource (no chat_id in the URL) — RLS narrows get_by_id to rows
    # this user's chats own; the explicit ChatRepository recheck is the
    # app-layer half of the same defense-in-depth (docs/SECURITY.md), same
    # pattern as DocumentRepository's flat DELETE endpoint.
    job = await job_repo.get_by_id(job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    await get_owned_chat_or_404(chat_repo, job.chat_id, user_id)
    return job


@router.get("/{job_id}", response_model=JobPublic)
async def get_job(job_id: uuid.UUID, db: RlsDbDep, current_user: CurrentUserDep) -> JobPublic:
    job = await _get_owned_job_or_404(
        JobRepository(db), ChatRepository(db), job_id, current_user.id
    )
    return JobPublic.model_validate(job)


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID, db: StreamingRlsDbDep, current_user: StreamingUserDep
) -> EventSourceResponse:
    # The browser connects to this endpoint directly (ADR-0007), so it
    # authenticates via a short-lived stream ticket rather than the httpOnly
    # session cookie (StreamingUserDep/StreamingRlsDbDep, ADR-0012).
    job_repo = JobRepository(db)
    chat_repo = ChatRepository(db)
    await _get_owned_job_or_404(job_repo, chat_repo, job_id, current_user.id)

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        last_stage: str | None = None
        while True:
            job = await job_repo.get_by_id(job_id)
            if job is None:
                yield {"event": "error", "data": '{"error_code": "not_found"}'}
                return
            if job.progress_stage != last_stage:
                last_stage = job.progress_stage
                yield {
                    "event": "stage",
                    "data": JobPublic.model_validate(job).model_dump_json(),
                }
            if job.status in _TERMINAL_STATUSES:
                return
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_stream())
