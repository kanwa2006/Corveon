"""Retrieval agent (blueprint §7) — semantic search over this chat's own
documents only (per-chat isolation, docs/ARCHITECTURE.md §5, ADR-0008). Never
queries another chat's vectors, even for the same user."""

from __future__ import annotations

from app.agents.state import Citation, OrchestratorState
from app.data.models.chunk import DocumentChunk
from app.data.models.document import Document

TOP_K = 5
# cosine similarity = 1 - cosine distance; below this, a hit isn't worth
# grounding on and is dropped rather than padding the prompt with noise.
MIN_SIMILARITY = 0.3


async def retrieve_citations(state: OrchestratorState) -> list[Citation]:
    has_chunks = await state.chunk_repo.has_ready_chunks(
        chat_id=state.chat_id, model_id=state.embedding_model.model_id
    )
    if not has_chunks:
        return []

    query_vector = state.embedding_model.embed_query(state.user_query)
    hits: list[tuple[DocumentChunk, Document, float]] = await state.chunk_repo.similarity_search(
        chat_id=state.chat_id,
        model_id=state.embedding_model.model_id,
        query_vector=query_vector,
        top_k=TOP_K,
    )
    return [
        Citation(
            chunk_id=chunk.id,
            document_id=doc.id,
            document_filename=doc.filename,
            ordinal=chunk.ordinal,
            similarity=round(1 - distance, 4),
            text=chunk.text,
        )
        for chunk, doc, distance in hits
        if (1 - distance) >= MIN_SIMILARITY
    ]


class RetrievalAgent:
    name = "retrieval"

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        state.citations = await retrieve_citations(state)
        return state
