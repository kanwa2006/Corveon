"""Job repository. ``GET /jobs/{id}`` is a flat resource (docs/API.md — no
chat_id in the URL), so ``get_by_id`` cannot take a chat_id predicate the way
every other content query does; isolation for this one lookup is enforced by
Postgres RLS on the RLS-scoped session (ADR-0013) plus an explicit
chat-ownership recheck in the router (defense in depth, docs/SECURITY.md)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.job import Job, JobStatus, JobType


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        # populate_existing: the progress-events SSE endpoint polls this
        # method repeatedly on one long-lived session. Without it, SQLAlchemy's
        # identity map would keep returning the first-loaded (increasingly
        # stale) Job object on every poll instead of the worker's committed
        # updates, even though each call does issue a fresh SELECT.
        result = await self._session.execute(
            select(Job).where(Job.id == job_id).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def create(self, *, chat_id: uuid.UUID, type_: JobType) -> Job:
        job = Job(chat_id=chat_id, type=type_)
        self._session.add(job)
        await self._session.flush()
        return job

    async def update_progress(
        self,
        job: Job,
        *,
        status: JobStatus | None = None,
        progress_stage: str | None = None,
        error: str | None = None,
    ) -> Job:
        if status is not None:
            job.status = status
        if progress_stage is not None:
            job.progress_stage = progress_stage
        if error is not None:
            job.error = error
        await self._session.flush()
        await self._session.refresh(job)
        return job
