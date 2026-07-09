"""Semantic search request/response schemas (docs/API.md — Search). In-chat
only — a search request always resolves against the chat_id in the URL."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    ordinal: int
    text: str
    similarity: float
