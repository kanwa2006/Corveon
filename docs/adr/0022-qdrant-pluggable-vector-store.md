# ADR-0022: Qdrant as a config-selected alternative to pgvector

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
ADR-0001 chose pgvector as the sole vector store, explicitly deferring Qdrant rather than
rejecting it, and named the seam that would make adopting it later possible: "retrieval is
behind a repository interface — so Qdrant can be adopted later without touching business
logic." Enterprise deployments (blueprint "Enterprise path") may outgrow pgvector's ~10M-vector
comfort zone, or may already run a dedicated Qdrant cluster and want Corveon to use it instead of
provisioning vector storage inside Postgres. Business logic (the search endpoint, the ingestion
pipeline, the reindex job, evidence retrieval) should not need to know or care which one is active.

## Decision
Introduce a `VectorStore` abstract base (`app/data/vectorstore/base.py`) with exactly the
operations `ChunkRepository` needs at the vector layer: `upsert`, `search`,
`has_vectors`, `embedded_chunk_ids` — all keyed by `(chat_id, model_id)`, operating on chunk
UUIDs and raw vectors, never on ORM-joined rows (a vector backend cannot return a joined
`Document` row; that join always happens against Postgres, where chunk text permanently lives
regardless of vector backend).

Two implementations:
- `PgvectorStore` (default) — the existing SQL, now behind the interface, session-bound like
  today.
- `QdrantStore` (opt-in) — a single `document_chunks` collection, `chat_id`/`model_id` stored as
  indexed payload fields and filtered on every call exactly like the SQL `WHERE` today (ADR-0008's
  no-cross-chat/no-cross-model-mixing invariant is enforced identically, just via a payload filter
  instead of a SQL predicate). Cosine distance, `vector(384)` to match `EMBEDDING_DIM`.

Selection is one new setting, `VECTOR_STORE: Literal["pgvector", "qdrant"] = "pgvector"`, read by
a `build_vector_store(settings, session) -> VectorStore` factory — the same config-gated-registration
shape as `build_provider_registry` (ADR-0006), just choosing one active implementation instead of
priority-ordered failover across many, since only one vector backend is ever active at a time.
`ChunkRepository` takes a `VectorStore` in its constructor and delegates every vector operation to
it; `bulk_create_chunks` (chunk text) is untouched, since chunk text always lives in Postgres.

## Consequences
- Business logic (search router, orchestrator's RAG retrieval, evidence verification, the
  ingestion/reindex worker tasks) is unchanged — all of it already went through
  `ChunkRepository`, never pgvector directly, so none of it names a vector-store backend
  (mirrors CLAUDE.md §5's "business logic never names a concrete AI provider").
  Only the ~5 call sites that construct a `ChunkRepository` now also build and pass a
  `VectorStore` alongside the existing `AsyncSession`.
- `similarity_search` becomes two queries instead of one SQL join (vector search for
  `(chunk_id, distance)` pairs, then a Postgres `IN` fetch for the matched chunks' text/document
  metadata) even on the default pgvector path — a deliberate, small overhead accepted for a real
  seam rather than a backend-specific fast path that would defeat the abstraction.
- Switching `VECTOR_STORE` for an existing deployment does not migrate vectors between backends —
  same posture as changing `EMBEDDING_MODEL_ID` (CLAUDE.md §6): old vectors are left in place, and
  chats need the existing reindex job (`reindex_chat_chunks`) re-run against the newly active
  backend before retrieval sees them there.
- One more optional external service for enterprise operators who choose it (`qdrant-client`
  dependency, `QDRANT_URL`/`QDRANT_API_KEY` settings) — zero footprint when unset, same
  "absence is not an error" posture as every other optional subsystem (§23.1).
- No Postgres schema change: `chunk_embeddings` keeps existing when `VECTOR_STORE=pgvector`;
  Qdrant stores its own copy of the vectors externally when selected. No Alembic migration in
  this change.

## Alternatives considered
- **Keep pgvector-only, revisit later:** rejected — the seam ADR-0001 promised already exists in
  `ChunkRepository`; implementing it now while the interface is small and fresh is cheaper than
  retrofitting it once more call sites depend on pgvector-specific return shapes.
- **Dual-write to both backends:** rejected — adds write-path complexity and a consistency problem
  (two systems that can silently diverge) for a feature meant to be a clean *alternative*, not a
  migration tool; a deployment picks one active backend.
- **Per-embedding-model Qdrant collections instead of one filtered collection:** rejected for now —
  today there is exactly one embedding model in use at a time; a single filtered collection matches
  the existing SQL `WHERE model_id = …` shape exactly and is simpler to reason about. Revisit if
  multiple concurrently-active embedding models becomes a real requirement.
