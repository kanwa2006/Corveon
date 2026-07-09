"""Unit tests for the Month 1 routing policy: Query Understanding
(app/agents/query_understanding.py) and Task Planning
(app/agents/task_planning.py)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.query_understanding import classify_intent
from app.agents.state import OrchestratorState, RoutingPath
from app.agents.task_planning import TaskPlanningAgent
from app.data.repositories.chunk_repository import ChunkRepository
from app.ingestion.embeddings import EmbeddingModel

pytestmark = pytest.mark.unit

_CHAT_ID = uuid.uuid4()


# ── Query Understanding ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    ["hi", "Hi!", "HELLO", "thanks", "thank you.", "ok", "sure!", "bye", "yes", "no", "k", ""],
)
def test_classify_intent_treats_conversational_turns_as_trivial(query: str) -> None:
    assert classify_intent(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "What treats a headache?",
        "Summarize this document.",
        "Is metformin safe with lisinopril?",
        "hi there, what does this report say about kidney function",
    ],
)
def test_classify_intent_treats_substantive_queries_as_not_trivial(query: str) -> None:
    assert classify_intent(query) is False


# ── Task Planning ────────────────────────────────────────────────────────


def _fake_embedding_model(vector: list[float] | None = None) -> EmbeddingModel:
    model = MagicMock(spec=EmbeddingModel)
    model.model_id = "test-model"
    model.embed_query.return_value = vector or [0.1, 0.2, 0.3]
    return model


def _state(chunk_repo: ChunkRepository, user_query: str) -> OrchestratorState:
    return OrchestratorState(
        chat_id=_CHAT_ID,
        user_query=user_query,
        chunk_repo=chunk_repo,
        embedding_model=_fake_embedding_model(),
    )


@pytest.mark.asyncio
async def test_plan_task_takes_fast_path_for_trivial_query_without_checking_documents() -> None:
    chunk_repo = AsyncMock(spec=ChunkRepository)

    result = await TaskPlanningAgent().run(_state(chunk_repo, "hi"))

    assert result.routing_path == RoutingPath.FAST_PATH
    assert result.citations == []
    chunk_repo.has_ready_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_plan_task_uses_pure_llm_when_chat_has_no_documents() -> None:
    chunk_repo = AsyncMock(spec=ChunkRepository)
    chunk_repo.has_ready_chunks.return_value = False

    result = await TaskPlanningAgent().run(_state(chunk_repo, "What treats a headache?"))

    assert result.routing_path == RoutingPath.PURE_LLM
    assert result.citations == []
    chunk_repo.similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_plan_task_uses_rag_no_match_when_no_chunk_clears_the_similarity_threshold() -> None:
    chunk_repo = AsyncMock(spec=ChunkRepository)
    chunk_repo.has_ready_chunks.return_value = True
    chunk_repo.similarity_search.return_value = []

    result = await TaskPlanningAgent().run(_state(chunk_repo, "What treats a headache?"))

    assert result.routing_path == RoutingPath.RAG_NO_MATCH
    assert result.citations == []


@pytest.mark.asyncio
async def test_plan_task_uses_rag_grounded_when_a_relevant_chunk_is_found() -> None:
    chunk_repo = AsyncMock(spec=ChunkRepository)
    chunk_repo.has_ready_chunks.return_value = True

    chunk = MagicMock(
        id=uuid.uuid4(), document_id=uuid.uuid4(), ordinal=0, text="Metformin treats T2D."
    )
    document = MagicMock(id=chunk.document_id, filename="doc.pdf")
    chunk_repo.similarity_search.return_value = [(chunk, document, 0.1)]  # similarity 0.9

    result = await TaskPlanningAgent().run(_state(chunk_repo, "What treats type 2 diabetes?"))

    assert result.routing_path == RoutingPath.RAG_GROUNDED
    assert len(result.citations) == 1
    assert result.citations[0].document_filename == "doc.pdf"
