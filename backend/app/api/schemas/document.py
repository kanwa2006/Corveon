"""Document/job request/response schemas (docs/API.md — Documents/uploads)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.data.models.document import DocumentStatus
from app.data.models.job import JobStatus


class DocumentPublic(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    page_count: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobPublic(BaseModel):
    id: uuid.UUID
    status: JobStatus
    progress_stage: str | None
    error: str | None

    model_config = {"from_attributes": True}


class UploadAcceptedResponse(BaseModel):
    job_id: uuid.UUID
