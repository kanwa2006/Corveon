"""Shared orchestrator state (blueprint §7: "a plain Python state-graph of
async nodes over a ... state object") — the one object threaded through every
agent's ``run()`` call. Each agent reads what it needs and writes its own
result field; nothing here is specific to one agent, which is what lets a new
agent (Evidence Verification, Medication-Safety Analysis, Month 3+) join the
pipeline by adding a field and a call, not by renegotiating existing agents'
signatures.

A plain dataclass, not a Pydantic model: every other field carries live
DB/model objects (``ChunkRepository``, ``EmbeddingModel``) that exist only
for this request's lifetime and are never (de)serialized — Pydantic's
validation-on-construction earns nothing here that a type-checked dataclass
doesn't already give for free (CLAUDE.md §5 reserves Pydantic for boundaries
validating *external* input, which this state object never is)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.data.repositories.chunk_repository import ChunkRepository
from app.ingestion.embeddings import EmbeddingModel


class RoutingPath(StrEnum):
    """The routing-policy outcome (CLAUDE.md §6), reduced to today's real
    capabilities. Month 3/6-12 add more branches (public evidence, org-
    trusted sources, multi-agent verification) as those subsystems land."""

    FAST_PATH = "fast_path"  # trivial input — retrieval skipped by policy (§23.5)
    PURE_LLM = "pure_llm"  # substantive query, but this chat has no documents to ground on
    RAG_GROUNDED = "rag_grounded"  # substantive query, relevant chunks found and used
    RAG_NO_MATCH = "rag_no_match"  # chat has documents, but none were relevant enough


@dataclass(frozen=True, slots=True)
class Citation:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    ordinal: int
    similarity: float
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "document_filename": self.document_filename,
            "ordinal": self.ordinal,
            "similarity": self.similarity,
        }


@dataclass(slots=True)
class OrchestratorState:
    chat_id: uuid.UUID
    user_query: str
    chunk_repo: ChunkRepository
    embedding_model: EmbeddingModel

    # Populated by agents as the pipeline runs — every field starts at its
    # "not yet decided" value so a caller inspecting state mid-pipeline (or a
    # test constructing one directly) can't mistake an unset field for a real
    # agent decision.
    is_trivial: bool | None = None
    routing_path: RoutingPath | None = None
    citations: list[Citation] = field(default_factory=list)
