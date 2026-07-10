# Architecture Decision Records

Each ADR captures one resolved decision — the context, the choice, and its consequences — so every
"why" in the blueprint is discoverable in-repo without external context (§23.7). ADRs are immutable
once `Accepted`; to change a decision, add a new ADR that supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-pgvector-over-qdrant.md) | pgvector (in Postgres) over a dedicated vector store | Accepted |
| [0002](0002-alembic-forward-only-migrations.md) | Alembic, forward-only, models↔migrations sync check | Accepted |
| [0003](0003-custom-orchestrator-over-langgraph.md) | Custom typed orchestrator over a heavyweight framework | Accepted |
| [0004](0004-ddinter-over-rxnav-ddi.md) | DDInter 2.0 + openFDA for DDIs (RxNav DDI API discontinued) | Accepted |
| [0005](0005-dual-renal-equations.md) | Dual renal equations (Cockcroft-Gault + 2021 CKD-EPI) | Accepted |
| [0006](0006-provider-agnostic-plugin-registry.md) | Provider-agnostic plugin registry; absence ≠ failure | Accepted |
| [0007](0007-sse-served-by-backend.md) | SSE served by the FastAPI backend, never Vercel serverless | Accepted |
| [0008](0008-embedding-model-versioning.md) | Embedding-model versioning + reindex on change | Accepted |
| [0009](0009-name-corveon.md) | Project name "Corveon" | Accepted |
| [0010](0010-apache-2-0-license.md) | Apache-2.0 license | Accepted |
| [0011](0011-arq-over-celery.md) | ARQ over Celery for the async task queue | Accepted |
| [0012](0012-frontend-auth-cookie-bff-proxy.md) | httpOnly-cookie session via Next.js Route Handler BFF proxy | Accepted |
| [0013](0013-postgres-rls-requires-nonsuperuser-app-role.md) | Postgres RLS requires a genuine non-superuser app role | Accepted |
| [0014](0014-local-disk-storage-fallback.md) | Local-disk object storage fallback when R2 is unconfigured | Accepted |
| [0015](0015-hnsw-index-via-raw-migration-ddl.md) | `chunk_embeddings` HNSW index via raw migration DDL, not a tracked model `Index` | Accepted |
| [0016](0016-sse-stream-ticket-bridge.md) | Short-lived stream ticket bridges httpOnly-cookie auth to direct-to-backend SSE | Accepted |
| [0017](0017-evidence-cache-via-redis-not-postgres-table.md) | External evidence cache lives in Redis, not a Postgres `external_cache` table | Accepted |
| [0018](0018-ddinter-loader-location-and-no-bundled-dataset.md) | DDInter loader lives in `backend/app/medication/`; the real dataset is never bundled | Accepted |

New ADRs use [`_template.md`](_template.md) and the next sequential number.
