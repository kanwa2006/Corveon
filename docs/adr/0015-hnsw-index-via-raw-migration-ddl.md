# ADR-0015: `chunk_embeddings` HNSW index defined via raw migration DDL, not a tracked model `Index`

- **Status:** Accepted
- **Date:** 2026-07-08

## Context
`docs/ARCHITECTURE.md` §4 specifies an HNSW index on `chunk_embeddings.embedding`. ADR-0002
requires every migration to produce an **empty** `alembic revision --autogenerate` diff against
the current models — CI enforces this on every PR. pgvector's HNSW index needs Postgres-specific
parameters (`postgresql_using="hnsw"`, `postgresql_ops={"embedding": "vector_cosine_ops"}`,
`postgresql_with={...}`) that Alembic's autogenerate reflects back from the live database with
lower fidelity than plain B-tree indexes — round-tripping through SQLAlchemy's `Index` construct
risks a spurious, permanent diff on this one index (a false CI failure on every future PR, not
just this one).

## Decision
Create the HNSW index with a raw `op.execute("CREATE INDEX ... USING hnsw (embedding
vector_cosine_ops)")` in migration `0003`, and do **not** declare it as a SQLAlchemy `Index` on the
`ChunkEmbedding` model. Distance metric is cosine (`vector_cosine_ops`), matching
`sentence-transformers` output normalized at embedding time (`app/ingestion/embeddings.py`).

Being absent from `Base.metadata` is necessary but **not sufficient** — verified empirically: a
fresh `alembic revision --autogenerate` against a live database that already has the index
proposed **dropping** it, because autogenerate reflects the live schema and treats anything absent
from `target_metadata` as an unwanted extra. The complete fix adds an `include_object` filter in
`migrations/env.py` that excludes this specific index (by name, `type_ == "index"`) from
autogenerate comparison entirely, in both directions.

## Consequences
- The empty-diff CI gate (ADR-0002) stays meaningful and never false-positives on this index.
- The index's existence is discoverable only via the migration file and the `include_object` filter
  in `env.py`, not via the model — documented there and with a comment on `ChunkEmbedding` pointing
  back to this ADR.
- Tradeoff: a future column rename/drop on `embedding` requires remembering to update the raw DDL
  and the `env.py` filter by hand; there is no autogenerate safety net for this one object.

## Alternatives considered
- **Declare as a SQLAlchemy `Index` with `postgresql_*` kwargs:** the "correct-looking" approach,
  but empirically risks non-deterministic autogenerate diffs for HNSW-with-ops indexes, which would
  break the sync-check gate for every subsequent PR, not just this one.
- **Skip the HNSW index for now (plain sequential scan):** matches nothing in
  `docs/ARCHITECTURE.md` and would silently degrade semantic search latency as chunk volume grows.
