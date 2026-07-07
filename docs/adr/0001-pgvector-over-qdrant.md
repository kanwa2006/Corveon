# ADR-0001: pgvector (in Postgres) over a dedicated vector store

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
Corveon needs vector similarity search for in-chat retrieval, with **absolute per-chat isolation**.
The team is a solo developer on free infrastructure. Candidate stores: pgvector inside PostgreSQL,
or a dedicated service such as Qdrant.

## Decision
Use **pgvector 0.8+ with an HNSW index**, `vector(384)`, inside PostgreSQL 16. Isolation filters
(`WHERE chat_id = :current_chat AND model_id = :active_model`) are ordinary SQL predicates joined
against relational tenancy data.

## Consequences
- One database, one operational surface — no second service to run, secure, or back up.
- SQL joins make the isolation invariant natural and enforceable (app guard + RLS + repo predicate).
- 2026 benchmarks show HNSW matches or beats dedicated stores under ~10M vectors.
- Tradeoff: past ~10M vectors pgvector's ceiling appears. We keep a **clean seam** — retrieval is
  behind a repository interface — so Qdrant can be adopted later without touching business logic.

## Alternatives considered
- **Qdrant / dedicated store:** stronger at very large scale, but adds a service, splits tenancy
  enforcement across systems, and is overkill below ~10M vectors. Deferred, not rejected forever.
