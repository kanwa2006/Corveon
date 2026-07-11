"""Task Planning agent (blueprint §7) — combines Query Understanding's intent
classification with this chat's own state (does it have documents, did
retrieval find anything relevant, did public evidence search find anything)
to pick a ``RoutingPath``. No always-on retrieval (CLAUDE.md §3): a trivial
query never even checks whether documents exist, and a query with documents
never triggers a public-evidence search (ADR-0021's branch is specifically
for the no-documents case)."""

from __future__ import annotations

from app.agents.public_evidence import PublicEvidenceAgent
from app.agents.query_understanding import QueryUnderstandingAgent
from app.agents.retrieval import RetrievalAgent
from app.agents.state import OrchestratorState, RoutingPath
from app.core.tracing import get_tracer

tracer = get_tracer(__name__)


class TaskPlanningAgent:
    name = "task_planning"

    def __init__(
        self,
        query_understanding: QueryUnderstandingAgent | None = None,
        retrieval: RetrievalAgent | None = None,
        public_evidence: PublicEvidenceAgent | None = None,
    ) -> None:
        self._query_understanding = query_understanding or QueryUnderstandingAgent()
        self._retrieval = retrieval or RetrievalAgent()
        self._public_evidence = public_evidence

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        with tracer.start_as_current_span("orchestrator.plan_task") as span:
            span.set_attribute("chat_id", str(state.chat_id))

            state = await self._query_understanding.run(state)
            if state.is_trivial:
                state.routing_path = RoutingPath.FAST_PATH
                span.set_attribute("routing.path", RoutingPath.FAST_PATH.value)
                return state

            has_documents = await state.chunk_repo.has_ready_chunks(
                chat_id=state.chat_id, model_id=state.embedding_model.model_id
            )
            if not has_documents:
                if self._public_evidence is not None:
                    state = await self._public_evidence.run(state)
                state.routing_path = (
                    RoutingPath.RAG_PUBLIC_EVIDENCE
                    if state.public_evidence
                    else RoutingPath.PURE_LLM
                )
                span.set_attribute("routing.path", state.routing_path.value)
                span.set_attribute("routing.public_evidence_count", len(state.public_evidence))
                return state

            state = await self._retrieval.run(state)
            state.routing_path = (
                RoutingPath.RAG_GROUNDED if state.citations else RoutingPath.RAG_NO_MATCH
            )
            span.set_attribute("routing.path", state.routing_path.value)
            span.set_attribute("routing.citation_count", len(state.citations))
            return state
