# ADR-0008: Embedding-model versioning and reindex on change

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
`chunk_embeddings.model_id` exists in the schema but needs a policy. Mixing vectors produced by
different embedding models in one similarity query silently degrades relevance, and a model upgrade
years later could poison results without warning (§23.4).

## Decision
- **Every similarity search filters by `model_id`** — vectors from different embedding models are
  never mixed in one query (queries filter by both `chat_id` and `model_id`).
- **Changing the default embedding model requires a background reindex job**, not in-place mixing.
- The **active embedding-model version is recorded in provenance**.

## Consequences
- Relevance stays consistent across model upgrades; no silent decay.
- Model migrations are explicit, observable ARQ jobs.
- Tradeoff: a reindex has compute cost; it is batched and runs in the async pipeline.

## Alternatives considered
- **Ignore `model_id` at query time:** simplest, but exactly the silent-decay failure we reject.
- **Hard-pin one model forever:** blocks future quality improvements.
