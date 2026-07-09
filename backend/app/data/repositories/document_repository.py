"""Document repository — every query scoped by chat_id (docs/ARCHITECTURE.md
§5) with one exception: ``DELETE /documents/{id}`` is a flat resource
(docs/API.md — no chat_id in the URL), so ``get_by_id`` cannot take a chat_id
predicate the way every other content query does. Isolation for that one
lookup is enforced by Postgres RLS on the RLS-scoped session (ADR-0013) plus
an explicit chat-ownership recheck in the router (defense in depth,
docs/SECURITY.md) — the same pattern as JobRepository.get_by_id. The
ingestion worker always has chat_id (passed through the ARQ job payload
alongside user_id, see app/workers/tasks.py), so it never needs this method."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.models.document import Document, DocumentStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_chat(self, chat_id: uuid.UUID) -> list[Document]:
        result = await self._session.execute(
            select(Document).where(Document.chat_id == chat_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_for_chat(
        self, document_id: uuid.UUID, chat_id: uuid.UUID
    ) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        chat_id: uuid.UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_key: str,
    ) -> Document:
        document = Document(
            chat_id=chat_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def update_status(
        self,
        document: Document,
        *,
        status: DocumentStatus,
        page_count: int | None = None,
        error: str | None = None,
    ) -> Document:
        document.status = status
        if page_count is not None:
            document.page_count = page_count
        if error is not None:
            document.error = error
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
