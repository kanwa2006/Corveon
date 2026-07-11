# ADR-0021: Public Evidence Retrieval agent (RAG-public-evidence routing branch)

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
The blueprint's full routing policy names seven branches (pure-LLM, RAG-uploaded, RAG-public-
evidence, hybrid, org-trusted, multi-agent verification, external-lookup); the orchestrator
(`app/orchestrator/chat_orchestrator.py`) has implemented four so far: fast-path, pure-LLM,
RAG-grounded, and RAG-no-match. Until now, a substantive clinical question in a chat with **no
uploaded documents** fell straight through to `PURE_LLM` — the model answers from its own
training data with zero retrieval, zero provenance, and zero citations. That directly contradicts
the mission (CLAUDE.md §1): "every important answer is grounded in transparent, multi-source
medical evidence with explicit provenance and confidence."

The Evidence Verification Engine (Month 3) already built everything needed to fill this gap: six
connectors (PubMed, DailyMed, openFDA, ClinicalTrials.gov, MeSH, RxNorm) behind a uniform
`EvidenceConnector.search(query, limit)` protocol, a registry that fans a query out to all six
concurrently (`EvidenceConnectorRegistry.search_all`), Redis-backed caching per connector, and a
retrieval function (`retrieve_evidence_for_claim`) that is — despite its claim-verification-era
name — already a generic "give me evidence for this text" call with no claim-specific logic in it.
That engine currently only runs **after** a message exists, as an opt-in "verify this message"
user action (`POST /chats/{id}/verify`), never proactively during response generation.

## Decision

**Add a fourth agent, `PublicEvidenceAgent` (`app/agents/public_evidence.py`), reusing
`retrieve_evidence_for_claim` unchanged** — no new connector code, no new retrieval logic, just a
thin `Agent`-protocol wrapper (matching `RetrievalAgent`'s own shape) that calls it with the raw
user query as the "claim" text. `TaskPlanningAgent` invokes it exactly where it invokes
`RetrievalAgent` today: when the query is substantive but this chat has **no** uploaded documents
(previously an unconditional `PURE_LLM`). A new `RoutingPath.RAG_PUBLIC_EVIDENCE` is set when the
agent finds at least one result across all six sources; `PURE_LLM` remains the fallback when it
finds nothing — an honest "no grounding available from either source" state, not a silent skip.

**Public evidence and uploaded-document citations stay separate, typed fields on
`OrchestratorState`** (`public_evidence: list[EvidenceResult]`, reusing the connector layer's own
`EvidenceResult` type directly rather than inventing a parallel one) — never merged into the
existing `citations: list[Citation]` field. The two provenance classes must never be blurred: a
chunk from the user's own upload and a PubMed abstract are different trust levels (blueprint's own
`source_class` taxonomy: `uploaded_document` vs `verified_public`), and the response-generation
prompt labels each block distinctly so the model (and, via `routing_trace`, the user) always knows
which is which.

**No claim-type classification before searching** — same "deliberately uniform" reasoning
`retrieve_evidence_for_claim`'s own docstring already gives for the verification use case: querying
all six sources with the raw query text, rather than a heuristic or extra LLM call to guess which
sources are relevant, keeps this deterministic-ish and avoids a second failure mode. An irrelevant
connector (e.g. ClinicalTrials.gov for a purely definitional question) just returns nothing useful,
per every connector's own contract.

## Consequences
- A first-time query in a document-less chat now costs up to six additional HTTP round-trips (one
  per connector) before the LLM call — mitigated by the existing Redis cache
  (`EVIDENCE_CACHE_TTL_SECONDS`) already in front of every connector, so a repeated or similar
  query across chats/users is cheap after the first hit. This is the same latency/cost tradeoff the
  existing Evidence Verification Engine already accepted for its own connector fan-out; nothing new
  is introduced here beyond widening when that fan-out runs.
- `routing_trace` grows a `public_evidence` array (empty unless this path fired) — additive, not a
  breaking change to the existing `retrieved_chunks`/`path`/`provider`/`status` shape.
- Org-trusted sources and full multi-agent verification (the two other blueprint branches still
  outstanding) are unaffected and remain future work — this ADR resolves one branch, not all three.

## Alternatives considered
- **Classify the query first (LLM call) to decide which connectors to search:** rejected — an extra
  LLM call per document-less message, plus a new failure mode (misclassification silently drops a
  relevant source), for a search-recall gain `retrieve_evidence_for_claim`'s existing design already
  argues isn't worth it.
- **Run public evidence retrieval unconditionally, even when the chat has documents:** rejected —
  the blueprint's RAG-uploaded branch already treats the user's own documents as sufficient
  grounding once retrieval finds a real hit; searching six external APIs on top of every grounded
  question would multiply cost/latency for no correctness benefit CLAUDE.md's own "RAG only when it
  helps" principle (§3) already argues against.
