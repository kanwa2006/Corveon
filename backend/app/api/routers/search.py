"""Semantic search endpoint (docs/API.md — Search). In-chat only — every
query filters by both chat_id and model_id (ADR-0008); never mixes another
chat's vectors into the result, even for the same user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, EmbeddingModelDep, RlsDbDep, SettingsDep
from app.api.routers._common import get_owned_chat_or_404
from app.api.schemas.search import SearchHit, SearchRequest
from app.data.repositories.chat_repository import ChatRepository
from app.data.repositories.chunk_repository import ChunkRepository
from app.data.vectorstore.registry import build_vector_store

router = APIRouter(prefix="/chats", tags=["search"])


@router.post("/{chat_id}/search", response_model=list[SearchHit])
async def search_chat(
    chat_id: uuid.UUID,
    payload: SearchRequest,
    db: RlsDbDep,
    current_user: CurrentUserDep,
    embedding_model: EmbeddingModelDep,
    settings: SettingsDep,
) -> list[SearchHit]:
    chat_repo = ChatRepository(db)
    await get_owned_chat_or_404(chat_repo, chat_id, current_user.id)

    chunk_repo = ChunkRepository(db, build_vector_store(settings, db))
    query_vector = embedding_model.embed_query(payload.query)
    hits = await chunk_repo.similarity_search(
        chat_id=chat_id,
        model_id=embedding_model.model_id,
        query_vector=query_vector,
        top_k=payload.top_k,
    )
    return [
        SearchHit(
            chunk_id=chunk.id,
            document_id=document.id,
            document_filename=document.filename,
            ordinal=chunk.ordinal,
            text=chunk.text,
            similarity=round(1 - distance, 4),
        )
        for chunk, document, distance in hits
    ]
