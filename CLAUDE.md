# CLAUDE.md — Corveon engineering contract

Terse, imperative rules for any agent working in this repo. Read fully before writing code.
Authoritative narrative lives in `docs/`; this file is the checklist that governs day-to-day work.

## 1. Mission & scope
Corveon is an open-source, provider-agnostic clinical intelligence platform. Defining stance:
**every uploaded document is potentially unreliable**; every important answer is grounded in
transparent, multi-source medical evidence with explicit provenance and confidence. It is a
human-in-the-loop assistant — it never replaces a licensed professional and never answers
confidently on suspected misinformation. Safety-first, evidence-before-response.

## 2. Architecture map (see docs/ARCHITECTURE.md for the full diagram)
Frontend (Next.js 16 / React 19) → API Gateway (FastAPI: auth, RBAC, rate limit, trace) →
{ AI Orchestrator (custom typed state-graph: routing + policy) · Domain Services (chats, docs,
users, analytics, audit) · Async Pipeline (ARQ workers on Redis) } → { Agent Runtime
(single-responsibility agents) · Data Layer (Postgres+pgvector, Redis, R2) · External Medical
APIs } → Provider-Agnostic AI Layer (Gemini · Claude · OpenAI · OpenRouter · Ollama, pools/failover).

## 3. Golden rules (non-negotiable)
- **Per-feature build order, every feature:** Architecture → Database → API → Backend → Frontend
  → Testing → Documentation. Do not skip validation to write more code.
- **Never fabricate** medical facts, citations, guidelines, dosages, or severities. A citation
  must resolve to a real source (PubMed/DOI/label record) or it is flagged, not shown.
- **RAG only when it helps** grounding/accuracy/explainability. No always-on retrieval. Trivial
  inputs take the orchestrator fast-path (single LLM call, no agent graph) — §23.5.
- **Per-chat isolation is absolute.** Every content query is filtered by `chat_id`. No cross-chat
  or global-memory read path. Cross-chat use requires an explicit user import action.
- **Rules engine is the source of truth** for medication safety. The LLM only (a) parses input
  into structured entries and (b) explains rule outputs — it may add no fact absent from them.
- **State uncertainty.** Surface confidence and provenance; recommend professional consultation.

## 4. Folder responsibilities (see docs/ARCHITECTURE.md §Repository)
- `backend/app/api/` — FastAPI routers; thin, contract-only, no business logic.
- `backend/app/orchestrator/` — routing policy + async state graph.
- `backend/app/agents/` — one file per single-responsibility agent (`run(state) -> state`).
- `backend/app/providers/` — provider adapters + key-pool/failover. **No business logic here.**
- `backend/app/evidence/` — verification engine + trusted-source connectors.
- `backend/app/medication/` — deterministic rules engine, RxNorm, DDI, renal, PIP.
- `backend/app/ingestion/` — parsers, OCR, chunking, embedding.
- `backend/app/data/` — SQLAlchemy models, repositories, RLS policies.
- `backend/app/core/` — config, security, logging, tracing.
- `backend/app/workers/` — ARQ tasks.
- `frontend/app` routes · `frontend/components` UI · `frontend/lib` api client/SSE/state.
- `data/loaders/` — pinned drug-data snapshot loaders. `infra/` — docker/compose/CI/deploy.

## 5. Coding conventions
- Type everything (Python: full annotations + Pydantic v2; TS: `strict`). Async-first.
- Small, single-responsibility modules. **Business logic never names a concrete AI provider** —
  go through the provider registry/router.
- Backend: `ruff` (lint+format), `mypy --strict`. Frontend: ESLint + Prettier, `tsc --noEmit`.
- Validate all external input with Pydantic / zod; agent outputs are schema-validated.

## 6. Data & migrations
- Alembic, one migration per change, **forward-only in prod**, human-reviewed. No auto-generated
  migration merges unreviewed. CI asserts models↔migrations are in sync.
- Every content-bearing table carries `chat_id`. Enforcement is triple: app guard + Postgres RLS
  + a repository layer that refuses queries lacking a `chat_id` predicate.
- Similarity search always filters by both `chat_id` and `model_id` — never mix embedding models
  in one query (§23.4). Changing the default embedding model requires a background reindex job.
- Drug data (DDInter 2.0, Beers 2023, STOPP/START v3, RxNorm) loads as pinned, checksummed
  snapshots recorded in `drug_data_snapshots` — reproducible and auditable.

## 7. Testing expectations (Definition of Done)
A feature is done only when **all relevant test layers pass in CI**: unit, integration
(Testcontainers), API contract (schemathesis), DB/migration + RLS isolation, auth/RBAC, pipeline,
security (bandit/pip-audit + injection/upload abuse), frontend unit (Vitest), e2e (Playwright),
a11y (axe-core). Medication rules use **golden tests** against pinned snapshots. See docs/DEVELOPER.md.

## 8. Security (see docs/SECURITY.md)
- Secrets via env only — never code, never DB. `.env` is gitignored.
- Validate every upload (MIME + magic-byte + size + extension allowlist + sandboxed parse).
- Treat document text as **data, not instructions** — delimited under a system-prompt contract;
  tool/agent invocation is orchestrator-gated, never triggered by document content.
- Audit-log sensitive actions (auth, uploads, exports, admin, evidence/medication findings).

## 9. Observability (see docs/DEBUGGING.md)
Every new code path adds an OpenTelemetry span + a structured (structlog JSON) log carrying
`trace_id`. Each agent call and provider call is its own span. Add Prometheus metrics on hot paths.

## 10. Debugging workflow
Reproduce → check the trace (`trace_id`) → check provider health → check job stage → **write the
failing test first**, then fix. Never silence an error with a bare fallback (see docs/SECURITY.md).

## 11. Documentation standards
Update the relevant doc (README / ARCHITECTURE / API / ENVIRONMENT / …) in the **same PR** as the
feature. New resolved decisions get an ADR in `docs/adr/`. The repo is never left undocumented.

## 12. Do-NOT list
- No always-on RAG. No cross-chat reads. No hardcoded/named providers in business logic.
- No unreviewed auto-migrations. No confident answers on suspected misinformation.
- No SSE or long-lived streams from Vercel serverless — SSE is served by the FastAPI backend (§23.3).
- No warnings/retries/errors for a provider that is simply *not configured* — absence ≠ failure (§23.1).
- No medical fact, dose, or citation the rules engine / a resolvable source did not supply.
